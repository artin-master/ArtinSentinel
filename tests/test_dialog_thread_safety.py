from pathlib import Path


def test_recorder_credentials_do_not_use_nested_dialog_exec():
    source = Path('artin_sentinel/app.py').read_text(encoding='utf-8')
    start = source.index('    def read_recorder_channels(self):')
    end = source.index('    def show_saved_channels(self):', start)
    recorder_flow = source[start:end]
    assert '.exec()' not in recorder_flow
    assert 'dialog.open()' in recorder_flow
    assert 'recorder_executor.submit' in recorder_flow
    assert 'QTimer' in source


def test_qrunnable_workers_are_retained():
    source = Path('artin_sentinel/app.py').read_text(encoding='utf-8')
    assert 'self.qt_workers = set()' in source
    assert 'self.qt_workers.add(worker)' in source
    assert 'self.qt_workers.discard(worker)' in source
