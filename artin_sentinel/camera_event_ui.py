"""Opt-in event controller. All database/widget work stays on the Qt thread."""
from queue import Empty

from .camera_events import CameraEventState


def history_message(row):
    from .camera_events import EVENT_TYPES
    import json
    if row['event_type'] not in EVENT_TYPES:
        return row['message']
    try:
        data = json.loads(row['message'])
    except (ValueError, TypeError):
        return row['message']
    if not isinstance(data, dict) or data.get('source') != 'dvrip-sofia':
        return row['message']
    labels = {'motion_start':'Movimento: início', 'motion_stop':'Movimento: fim', 'human_start':'Pessoa: início', 'human_stop':'Pessoa: fim', 'alarm_unknown':'Evento local não classificado'}
    scope = f"canal cadastrado #{data['channel_id']}" if type(data.get('channel_id')) is int else 'equipamento (canal não correlacionado)'
    reason = {'safety_timeout':'expiração de segurança; Stop não recebido', 'subscription_stopped':'sonda encerrada', 'notification':'notificação local'}.get(data.get('reason'), 'notificação local')
    return f"{labels[row['event_type']]} • {scope} • DVRIP/Sofia • {reason}"


class CameraEventUi:
    def _ensure_camera_events(self):
        if not hasattr(self, '_camera_event_workers'):
            self._camera_event_workers = {}
            self._camera_event_bindings = {}
            self._camera_event_retired = []
            self._camera_event_state = CameraEventState(self._persist_camera_event)
            self._camera_history_dirty = False
            self._camera_event_notices = {}

    def _persist_camera_event(self, device, event):
        self.db.add_camera_event(device, event)
        self._camera_history_dirty = True
        if event.reason == "notification":
            self._record_camera_event_evidence(device, kind=event.kind)

    def _stop_camera_event_device(self, device):
        worker = self._camera_event_workers.pop(device, None)
        binding = self._camera_event_bindings.pop(device, None)
        if worker:
            worker.stop()
            self._camera_event_retired.append((device, worker))
        row = self.db.get_device(device)
        if row is not None and (binding is None or row["site_id"] == binding[0]):
            # A removed channel must not create an end record on another scope.
            for key, (event, deadline) in list(self._camera_event_state.active.items()):
                if key[0] == device and event.channel is not None and self.db.get_recorder_channel(event.channel) is None:
                    del self._camera_event_state.active[key]
            self._camera_event_state.clear_device(device)
        else:
            self._camera_event_state.active = {key:value for key,value in self._camera_event_state.active.items() if key[0] != device}

    def stop_camera_events(self):
        if not hasattr(self, '_camera_event_workers'):
            return
        for device in list(self._camera_event_workers):
            self._stop_camera_event_device(device)
        # Shared shutdown budget, never N times four seconds.
        import time
        deadline = time.monotonic() + 4
        for device, worker in self._camera_event_retired:
            worker.wait(max(0, deadline - time.monotonic()))

    def poll_camera_events(self):
        if getattr(self, '_closing_app', False) or not hasattr(self, '_camera_event_workers'):
            return
        self._camera_event_retired = [(d,w) for d,w in self._camera_event_retired if not w.wait(0)]
        for device_id, worker in list(self._camera_event_workers.items()):
            site, host, mapping = self._camera_event_bindings[device_id]
            device = self.db.get_device(device_id)
            if device is None or device['site_id'] != site or device['ip'] != host or site != self.current_site_id:
                self._stop_camera_event_device(device_id)
                continue
            support = worker.snapshot().support
            if support in {"yes", "no"}:
                self._record_camera_event_evidence(device_id, support=support)
            # Refresh inventory mapping without guessing from channel_no.
            from .camera_events import verified_event_channels
            mapping = verified_event_channels(device, self.db.list_recorder_channels(device_id))
            for _ in range(128):
                try:
                    event = worker.events.get_nowait()
                except Empty:
                    break
                self._camera_event_state.ingest(device_id, event, mapping)
        self._camera_event_state.expire()
        self.refresh_camera_event_badges()
        if self._camera_history_dirty and hasattr(self, 'event_table'):
            self._camera_history_dirty = False
            self._refresh_camera_event_history()

    def _refresh_camera_event_history(self):
        from PySide6.QtWidgets import QTableWidgetItem
        events = self.db.list_events()
        self.event_table.setRowCount(len(events))
        for row, event in enumerate(events):
            values = (event['created_at'], event['severity'], event['event_type'], event['device_name'] or '—', history_message(event))
            for col, value in enumerate(values):
                self.event_table.setItem(row, col, QTableWidgetItem(str(value)))

    def refresh_camera_event_badges(self):
        state = getattr(self, '_camera_event_state', None)
        tiles = list(getattr(self, 'video_tiles', []))
        for window in getattr(self, 'detached_windows', {}).values():
            tiles.extend(window.video_tiles)
        for tile in tiles:
            source = tile.source or {}
            device, channel = source.get('device_id'), source.get('channel_id')
            # Equipment-level events intentionally never mark a channel tile.
            tile.set_camera_event_badge(state.labels(device, channel) if state and channel is not None else '')
        selected = getattr(self, 'selected_video_tile', None)
        source = selected.source or {} if selected else {}
        device = source.get('device_id')
        label = getattr(self, 'camera_event_status', None)
        if label:
            equipment = state.labels(device, None) if state else ''
            worker = getattr(self, '_camera_event_workers', {}).get(device)
            status = worker.snapshot() if worker else None
            states = {'connecting':'conectando', 'active':'assinatura ativa', 'reconnecting':'reconectando', 'unsupported':'dialeto não suportado', 'refused':'assinatura recusada', 'stopped':'parada'}
            text = f"Eventos locais: {states.get(status.state, 'desconhecido')}" if status else 'Eventos locais: sonda desligada'
            if not status:
                text = getattr(self, '_camera_event_notices', {}).get(device, text)
            if equipment:
                text += f'\nEquipamento: {equipment} (canal não correlacionado)'
            label.setText(text)
            if device:
                diagnostic = self.camera_event_diagnostic_text(device)
                label.setToolTip(diagnostic)
                self._update_camera_event_diagnostic_panel(device, diagnostic)
        if hasattr(self, 'camera_event_action'):
            device_row = self.db.get_device(device) if device else None
            eligible = bool(device_row and device_row['provider'] == 'it-blue')
            self.camera_event_action.setEnabled(eligible)
            self.camera_event_diagnostics_action.setEnabled(eligible)
            self.camera_event_action.blockSignals(True)
            self.camera_event_action.setChecked(device in getattr(self, '_camera_event_workers', {}))
            self.camera_event_action.blockSignals(False)

    def toggle_camera_event_probe(self, checked=False):
        from ipaddress import ip_address
        from .dvrip_events import EventWorker
        from .camera_events import verified_event_channels
        self._ensure_camera_events()
        tile = getattr(self, 'selected_video_tile', None)
        source = tile.source or {} if tile else {}
        device_id = source.get('device_id')
        device = self.db.get_device(device_id) if device_id else None
        if not device or device['provider'] != 'it-blue' or device['site_id'] != self.current_site_id:
            self.refresh_camera_event_badges()
            return
        if device_id in self._camera_event_workers:
            self._stop_camera_event_device(device_id)
            self.refresh_camera_event_badges()
            return
        if any(d == device_id and not w.wait(0) for d,w in self._camera_event_retired):
            self._camera_probe_notice(device_id, 'Eventos locais: aguardando encerramento da sonda anterior')
            return
        try:
            target = ip_address(device['ip'])
            if target.is_loopback or target.is_unspecified or target.is_multicast:
                raise ValueError()
        except ValueError:
            self._camera_probe_notice(device_id, 'Eventos locais: requer endpoint IP local válido')
            return
        # Opt-in family probe is not a capability claim; no cloud/tunnel guessing.
        credentials = self._credentials_for_device(device_id)
        if credentials is None:
            self._camera_probe_notice(device_id, 'Eventos locais: credencial local necessária')
            return
        self._camera_event_notices.pop(device_id, None)
        worker = EventWorker(str(target), *credentials)
        self._camera_event_bindings[device_id] = (
            device['site_id'], device['ip'], verified_event_channels(device, self.db.list_recorder_channels(device_id)),
        )
        self._camera_event_workers[device_id] = worker
        worker.start()
        self.refresh_camera_event_badges()

    def camera_event_diagnostic_text(self, device_id):
        from .talkback import sanitize_talkback_diagnostic
        from .log_viewer import sanitize_log_text
        device = self.db.get_device(device_id) if device_id else None
        if device is None:
            return 'Eventos locais: nenhum equipamento selecionado.'
        worker = getattr(self, '_camera_event_workers', {}).get(device_id)
        diag = worker.snapshot() if worker else None
        state = getattr(self, '_camera_event_state', None)
        event = state.last.get(device_id) if state else None
        username, password = self._credentials_for_device(device_id) or ('', '')
        model = sanitize_log_text(sanitize_talkback_diagnostic(device['model'], username, password))
        firmware = sanitize_log_text(sanitize_talkback_diagnostic(device['firmware'], username, password))
        support = {'yes':'sim (assinatura aceita; tipos dependem de eventos recebidos)', 'no':'não suportado neste dialeto', 'unknown':'desconhecido'}
        from datetime import datetime, timezone
        reconnect = datetime.fromtimestamp(diag.last_reconnect, timezone.utc).isoformat(timespec='seconds') if diag and diag.last_reconnect else '—'
        lines = [
            'Eventos locais DVRIP/Sofia — sonda opt-in, somente leitura',
            f'Modelo: {model or "—"} • Firmware: {firmware or "—"}',
            f'Suporte: {support[diag.support if diag else "unknown"]}',
            f'Assinatura ativa: {"sim" if diag and diag.active else "não"}',
            f'Último evento: {event.kind if event else "—"}',
            f'Canal cadastrado: {event.channel if event and event.channel is not None else "equipamento / não correlacionado"}',
            f'Índice informado pelo firmware: {event.native_channel if event and event.native_channel is not None else "—"} (sem inferência de lente)',
            f'Recebido em: {event.received_at if event else "—"}',
            f'Último reconnect: {reconnect}',
            f'Erro: {diag.error_code or "—" if diag else "—"}',
            f'Fila: {diag.dropped if diag else 0} notificações descartadas por limite',
            'Configuração detectada (não representa estado físico de luz/sirene):',
        ]
        if diag and diag.config:
            lines.extend(f'{path}: {value}' for path,value in diag.config)
        else:
            lines.append('Nenhum campo permitido confirmado; ausência não comprova falta de suporte.')
        lines.append('Motion/Human e a correlação de canal precisam de teste físico. Nenhum acionamento de luz/sirene é enviado.')
        return '\n'.join(lines)

    def show_camera_event_diagnostics(self):
        self.live_diag_panel.show()
        self.refresh_live_diagnostic_panel()

    def _record_camera_event_evidence(self, device_id, *, support=None, kind=None):
        """Inventory-only LAN observations; never publish/promote AKDB capability."""
        import json
        from .camera_events import EVENT_TYPES, timestamp
        device = self.db.get_device(device_id)
        if device is None:
            return
        try:
            metadata = json.loads(device['metadata_json'] or '{}')
        except (ValueError, TypeError, KeyError, IndexError):
            metadata = {}
        previous = metadata.get('dvrip_event_evidence', {}) if isinstance(metadata, dict) else {}
        previous = previous if isinstance(previous, dict) else {}
        observed = previous.get('normalized_types_observed', [])
        observed = sorted(set(value for value in observed if isinstance(value, str) and value in EVENT_TYPES)) if isinstance(observed, list) else []
        if kind in EVENT_TYPES and kind not in observed:
            observed.append(kind)
        subscription = support or previous.get('subscription', 'unknown')
        if subscription not in {'yes', 'no', 'unknown'}:
            subscription = 'unknown'
        evidence = {
            'subscription': subscription,
            'normalized_types_observed': sorted(observed),
            'source': 'local_protocol_observation',
            'confidence': 'protocol_response_only',
            'physical_validation': 'pending',
            'homologated': False,
        }
        if all(previous.get(key) == value for key,value in evidence.items()):
            return
        evidence['observed_at'] = timestamp()
        self.db.merge_device_metadata(device_id, {'dvrip_event_evidence': evidence})

    def _camera_probe_notice(self, device_id, message):
        self._camera_event_notices[device_id] = message
        self.refresh_camera_event_badges()

    def append_camera_event_diagnostic(self, device_id):
        text = self.camera_event_diagnostic_text(device_id)
        self.live_diag_panel.appendPlainText(text)
        self._camera_diag_rendered = (device_id, text)

    def _update_camera_event_diagnostic_panel(self, device_id, text):
        panel = getattr(self, 'live_diag_panel', None)
        previous = getattr(self, '_camera_diag_rendered', None)
        if panel is None or not panel.isVisible() or not previous or previous[0] != device_id or previous[1] == text:
            return
        contents = panel.toPlainText()
        if previous[1] not in contents:
            return
        scroll = panel.verticalScrollBar().value()
        panel.setPlainText(contents.replace(previous[1], text, 1))
        panel.verticalScrollBar().setValue(scroll)
        self._camera_diag_rendered = (device_id, text)
