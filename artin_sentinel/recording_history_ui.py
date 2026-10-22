"""Read-only recording calendar; network work never runs in the GUI thread."""
import calendar
from datetime import date, timedelta
from queue import Queue, Empty
from threading import Event, Thread
from PySide6.QtCore import QDate, QDateTime, QTime, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QTextCharFormat
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                              QCalendarWidget, QDateEdit, QDateTimeEdit, QProgressBar)
from .recording_history import HistoryCache, run_history


class RecordingDateEdit(QDateTimeEdit):
    """Keep direct time editing; date clicks open the recording-aware calendar."""
    historyRequested = Signal()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and event.position().x() >= self.width() - 26:
            self.historyRequested.emit(); event.accept(); return
        super().mousePressEvent(event)
        if event.button() == Qt.LeftButton and self.currentSection() in (self.DaySection, self.MonthSection, self.YearSection):
            self.historyRequested.emit()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_F4 or (event.key() == Qt.Key_Down and event.modifiers() & Qt.AltModifier):
            self.historyRequested.emit(); event.accept(); return
        super().keyPressEvent(event)


def select_day(owner, day):
    owner.playback_start.setDateTime(QDateTime(day, QTime(0, 0)))
    owner.playback_end.setDateTime(QDateTime(day.addDays(1), QTime(0, 0)))
    if getattr(owner, "_playback_day_mode", False):
        from .playback_layout import queue_day_search
        queue_day_search(owner)


def add_history_controls(owner, layout):
    row = QHBoxLayout()
    day = QPushButton('Buscar neste dia')
    def search_day():
        select_day(owner, owner.playback_start.date())
        owner.search_playback_recordings()
    day.clicked.connect(search_day)
    owner.playback_start.historyRequested.connect(lambda: open_history(owner, owner.playback_start.date()))
    owner.playback_end.historyRequested.connect(lambda: open_history(owner, owner.playback_end.date()))
    row.addWidget(day); layout.addLayout(row)


def open_history(owner, selected_day=None):
    from .access_control import authorize
    if not authorize(owner,'playback'):return
    current = getattr(owner, '_recording_history_dialog', None)
    if current is not None and current.busy:
        current.show(); current.raise_(); return
    device_id = owner.playback_device_combo.currentData()
    channels = owner.selected_playback_channels()
    device = owner.db.get_device(device_id) if device_id is not None else None
    if not device or len(channels) != 1:
        owner.playback_status.setText('Selecione um único canal para consultar o histórico.'); return
    credentials = owner._credentials_for_device(int(device_id))
    if credentials is None:
        owner.playback_status.setText('Informe a credencial do gravador antes de consultar o histórico.'); return
    route, _ = owner.playback_channel_endpoint(int(device_id), channels[0])
    dialog = RecordingHistoryDialog(owner, dict(device), route, credentials, channels[0], automatic=True, selected_day=selected_day)
    owner._recording_history_dialog = dialog
    dialog.show()


class RecordingHistoryDialog(QDialog):
    def __init__(self, owner, device, route, credentials, channel, *, automatic=False, selected_day=None):
        super().__init__(owner, Qt.Tool)
        self.owner = owner; self.device = device; self.route = route
        self.credentials = credentials; self.channel = channel
        self.cache = HistoryCache(owner.db.path.parent / 'recording-history-cache.json')
        self.scope = str(owner.db.path.resolve()) + '/' + str(device['id']) + '/' + route + '/' + str(channel)
        from .hik_sdk import settings as hik_sdk_settings,sdk_channel
        sdk_options=hik_sdk_settings(device)
        if sdk_options['enabled']:
            self.scope+='/hik-sdk/'+str(sdk_options['port'])+'/'+str(sdk_channel(device,channel))
        self.busy = False; self.cancel_event = Event(); self.messages = Queue()
        self.automatic = automatic; self.pending_month = False; self.closing = False; self.job_oldest = False
        self.month_debounce = QTimer(self); self.month_debounce.setSingleShot(True)
        self.month_debounce.setInterval(250); self.month_debounce.timeout.connect(self.query_visible_month)
        self.setWindowTitle(f'Histórico de gravações • canal {channel}')
        self.resize(660, 620)
        layout = QVBoxLayout(self)
        note = QLabel('Selecione um dia para usar suas 24 horas. Horário local do DVR.\n'
                      'O mês é consultado em segundo plano; resultados em cache valem por até 12 horas.' if automatic else
                      'Horário local do DVR. Consultar mês verifica a disponibilidade de cada dia.')
        note.setWordWrap(True); layout.addWidget(note)
        self.calendar = QCalendarWidget(); self.calendar.setGridVisible(True)
        self.calendar.setMaximumDate(QDate.currentDate())
        self.calendar.setSelectedDate(selected_day or owner.playback_start.date())
        self.calendar.currentPageChanged.connect(self.page_changed)
        self.calendar.selectionChanged.connect(self.describe_day)
        if automatic: self.calendar.clicked.connect(lambda _day: self.use_day())
        layout.addWidget(self.calendar)
        legend = QLabel('Verde: gravação • Cinza: sem gravação • Âmbar: falha/incompleto\nSem cor: não consultado ou cache expirado')
        legend.setWordWrap(True); layout.addWidget(legend)
        self.day_note = QLabel(); self.day_note.setWordWrap(True); layout.addWidget(self.day_note)
        row = QHBoxLayout()
        self.month_btn = QPushButton('Atualizar mês' if automatic else 'Consultar mês'); self.month_btn.clicked.connect(self.query_month)
        self.use_btn = QPushButton('Usar este dia'); self.use_btn.clicked.connect(self.use_day)
        row.addWidget(self.month_btn); row.addWidget(self.use_btn); layout.addLayout(row)
        row = QHBoxLayout(); row.addWidget(QLabel('Limite retroativo:'))
        self.limit = QDateEdit(QDate.currentDate().addDays(-90)); self.limit.setCalendarPopup(True)
        self.limit.setDisplayFormat('dd/MM/yyyy'); self.limit.setMinimumDate(QDate.currentDate().addYears(-10))
        self.limit.setMaximumDate(QDate.currentDate()); row.addWidget(self.limit)
        self.oldest_btn = QPushButton('Localizar mais antiga'); self.oldest_btn.clicked.connect(self.query_oldest)
        row.addWidget(self.oldest_btn); layout.addLayout(row)
        self.progress = QProgressBar(); self.progress.setRange(0, 1); layout.addWidget(self.progress)
        self.status = QLabel('Nenhuma consulta iniciada.'); self.status.setWordWrap(True); layout.addWidget(self.status)
        row = QHBoxLayout(); self.cancel_btn = QPushButton('Cancelar consulta')
        self.cancel_btn.setEnabled(False); self.cancel_btn.clicked.connect(self.cancel)
        close = QPushButton('Fechar'); close.clicked.connect(self.reject)
        row.addWidget(self.cancel_btn); row.addWidget(close); layout.addLayout(row)
        self.timer = QTimer(self); self.timer.setInterval(100); self.timer.timeout.connect(self.poll)
        self.paint_days()
        if automatic: self.month_debounce.start()

    def page_changed(self, *_args):
        self.paint_days()
        if self.automatic and not self.closing: self.month_debounce.start()

    def query_visible_month(self):
        if self.closing: return
        if self.busy:
            self.pending_month = True; self.cancel(); return
        year, month = self.calendar.yearShown(), self.calendar.monthShown()
        days = [date(year, month, n) for n in range(1, calendar.monthrange(year, month)[1] + 1)]
        days = [day for day in days if day <= date.today() and self.cache.get(self.scope, day) is None]
        if days: self.start(days, False)
        else: self.status.setText("Mês disponível em cache. Use Atualizar mês para consultar novamente.")

    def describe_day(self):
        day = self.calendar.selectedDate().toPython(); entry = self.cache.get(self.scope, day)
        labels = {'recorded': 'Gravação encontrada', 'empty': 'Consulta completa sem gravações',
                  'error': 'Consulta falhou; disponibilidade desconhecida', 'partial': 'Consulta incompleta'}
        self.day_note.setText((labels[entry.state] + f' • consultado {entry.checked_at:%d/%m %H:%M}') if entry else 'Dia não consultado ou cache expirado.')

    def paint_days(self):
        year = self.calendar.yearShown(); month = self.calendar.monthShown()
        colors = {'recorded': '#247745', 'empty': '#647080', 'error': '#a36517', 'partial': '#a36517'}
        for number in range(1, calendar.monthrange(year, month)[1] + 1):
            day = date(year, month, number); entry = self.cache.get(self.scope, day)
            fmt = QTextCharFormat()
            if entry:
                fmt.setBackground(QColor(colors[entry.state])); fmt.setForeground(QColor('white'))
                fmt.setToolTip({'recorded':'Gravação encontrada','empty':'Sem gravações na consulta completa',
                                'error':'Falha na consulta','partial':'Consulta incompleta'}[entry.state])
            self.calendar.setDateTextFormat(QDate(year, month, number), fmt)
        self.describe_day()

    def use_day(self):
        # A modeless dialog must not apply a date to another recorder accidentally.
        if (self.owner.playback_device_combo.currentData() != self.device['id']
                or self.owner.selected_playback_channels() != (self.channel,)):
            self.status.setText('Selecione novamente o gravador e o canal originais antes de usar este dia.'); return
        select_day(self.owner, self.calendar.selectedDate())
        self.owner.playback_status.setText(f'Dia selecionado para o canal {self.channel}. Consulta automática agendada.' if getattr(self.owner,"_playback_day_mode",False) else f'Dia selecionado para o canal {self.channel}. Clique em Buscar gravações.')
        self.accept()

    def query_month(self):
        year = self.calendar.yearShown(); month = self.calendar.monthShown()
        days = [date(year, month, n) for n in range(1, calendar.monthrange(year, month)[1] + 1)]
        self.start([d for d in days if d <= date.today()], False)

    def query_oldest(self):
        begin = self.limit.date().toPython(); today = date.today()
        self.start([begin + timedelta(days=n) for n in range((today - begin).days + 1)], True)

    def start(self, dates, oldest):
        if self.busy or not dates: return
        self.busy = True; self.cancel_event = Event(); self.job_oldest = oldest
        self.month_btn.setEnabled(False); self.oldest_btn.setEnabled(False); self.use_btn.setEnabled(True)
        self.cancel_btn.setEnabled(True); self.progress.setRange(0, len(dates)); self.progress.setValue(0)
        self.status.setText('Consultando um dia por vez… Cancelar mantém os dias já verificados.')
        # Snapshot all inputs before entering the worker; it never reads Qt or the DB.
        device, route, credentials, channel = self.device, self.route, self.credentials, self.channel
        cancel, messages = self.cancel_event, self.messages
        def work():
            try:
                result = run_history(device, route, *credentials, channel, dates, oldest=oldest,
                                     cancel_event=cancel, progress=lambda *args: messages.put(('progress', args)))
                messages.put(('result', result))
            except Exception as exc:
                messages.put(('error', type(exc).__name__))
        Thread(target=work, name='recording-history', daemon=True).start()
        self.timer.start()

    def cancel(self):
        self.cancel_event.set(); self.status.setText('Cancelando a consulta atual…')
        self.cancel_btn.setEnabled(False)

    def poll(self):
        while True:
            try: kind, value = self.messages.get_nowait()
            except Empty: break
            if kind == 'progress':
                done, total, check = value
                try: self.cache.put(self.scope, check)
                except OSError: pass
                self.progress.setValue(done)
                self.status.setText(f'Verificados {done}/{total} dias • {check.day:%d/%m/%Y}')
                self.paint_days()
            else:
                self.busy = False; self.timer.stop(); self.month_btn.setEnabled(True)
                self.oldest_btn.setEnabled(True); self.use_btn.setEnabled(True); self.cancel_btn.setEnabled(False)
                if self.pending_month and not self.closing:
                    self.pending_month = False; self.month_debounce.start()
                if kind == 'error':
                    self.status.setText('Consulta não concluída (' + value + '). Confira o acesso ao gravador.'); continue
                if self.automatic and not self.job_oldest:
                    year, month = self.calendar.yearShown(), self.calendar.monthShown()
                    counts = {'recorded':0, 'empty':0, 'partial':0, 'error':0, 'unknown':0}
                    for number in range(1, calendar.monthrange(year, month)[1] + 1):
                        day = date(year, month, number)
                        if day > date.today(): continue
                        entry = self.cache.get(self.scope, day)
                        counts[entry.state if entry else 'unknown'] += 1
                    self.status.setText(f"Dias: {counts['recorded']} com gravação; {counts['empty']} sem gravação; "
                                        f"{counts['partial']+counts['error']} incompletos/falhas; {counts['unknown']} não consultados."
                                        + (' Consulta cancelada.' if value.cancelled else ''))
                    continue
                interval = f'{value.range_start:%d/%m/%Y} a {value.range_end:%d/%m/%Y}'
                if value.earliest:
                    text = f'Mais antiga encontrada no intervalo: {value.earliest:%d/%m/%Y %H:%M:%S}.'
                elif value.verified:
                    text = 'Nenhuma gravação encontrada no intervalo consultado.'
                else:
                    text = 'Não foi possível determinar a gravação mais antiga.'
                if not value.verified: text += ' Verificação incompleta' + (' (cancelada).' if value.cancelled else ' (falhas ou dados parciais).')
                self.status.setText(text + '\nIntervalo: ' + interval + '. Não determina o limite absoluto de retenção do DVR.')

    def done(self, result):
        self.closing = True; self.pending_month = False; self.month_debounce.stop()
        if self.busy: self.cancel()
        super().done(result)
