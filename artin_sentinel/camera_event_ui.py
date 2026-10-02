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

    def _persist_camera_event(self, device, event):
        self.db.add_camera_event(device, event)
        self._camera_history_dirty = True

    def _stop_camera_event_device(self, device):
        worker = self._camera_event_workers.pop(device, None)
        self._camera_event_bindings.pop(device, None)
        if worker:
            worker.stop()
            self._camera_event_retired.append((device, worker))
        if self.db.get_device(device) is not None:
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
            # Refresh inventory mapping without guessing from channel_no.
            from .camera_events import correlated_channels
            mapping = correlated_channels(self.db.list_recorder_channels(device_id))
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
            text = f"Eventos locais: {status.state}" if status else 'Eventos locais: sonda desligada'
            if equipment:
                text += f'\nEquipamento: {equipment} (canal não correlacionado)'
            label.setText(text)
        if hasattr(self, 'camera_event_action'):
            device_row = self.db.get_device(device) if device else None
            eligible = bool(device_row and device_row['provider'] == 'it-blue')
            self.camera_event_action.setEnabled(eligible)
            self.camera_event_action.blockSignals(True)
            self.camera_event_action.setChecked(device in getattr(self, '_camera_event_workers', {}))
            self.camera_event_action.blockSignals(False)
