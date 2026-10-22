from artin_sentinel.pc_capacity import estimate_capacity,PressureWarning


def test_healthy_measurement_estimates_same_profile_with_margin():
    samples=[dict(channels=4,cpu=40,system_cpu=45,available_mb=8000,rss_mb=400,fps_ratio=.98,stable=True) for _ in range(10)]
    result=estimate_capacity(samples)
    assert result['measured']==4 and 4<=result['recommended']<=8
    assert result['estimated'] and 'perfil' in result['note']


def test_unstable_or_short_measurement_does_not_invent_capacity():
    assert estimate_capacity([])['recommended'] is None
    samples=[dict(channels=4,cpu=40,system_cpu=45,available_mb=8000,rss_mb=400,fps_ratio=.98,stable=False) for _ in range(10)]
    assert estimate_capacity(samples)['recommended'] is None


def test_sustained_pressure_warns_with_cooldown():
    warning=PressureWarning()
    sample=dict(channels=4,cpu=90,system_cpu=95,available_mb=400,rss_mb=400,fps_ratio=.5,stable=True)
    assert not warning.update(sample,0)
    assert not warning.update(sample,3)
    assert warning.update(sample,6)
    assert not warning.update(sample,9)
    assert not warning.update(dict(sample,cpu=10,system_cpu=10,available_mb=8000,fps_ratio=1),12)


def test_report_does_not_extrapolate_on_low_frame_delivery():
    samples=[dict(channels=8,cpu=30,system_cpu=40,available_mb=8000,rss_mb=400,fps_ratio=.2,stable=True) for _ in range(10)]
    assert estimate_capacity(samples)['recommended'] is None


def test_pc_dialog_outputs_capacity_and_cancel_preserves_streams(monkeypatch):
    from PySide6.QtWidgets import QApplication,QWidget
    import shiboken6
    from types import SimpleNamespace
    from artin_sentinel.pc_capacity_ui import PCAnalysisDialog
    global _APP
    _APP=QApplication.instance() or QApplication([]);owner=QWidget()
    import time
    samples=[(time.monotonic()+1,dict(channels=4,cpu=40,system_cpu=45,available_mb=8000,rss_mb=400,fps_ratio=.98,stable=True,profiles=['Sub'])) for _ in range(10)]
    owner._pc_monitor=SimpleNamespace(samples=samples,latest=samples[-1][1])
    dialog=PCAnalysisDialog(owner)
    dialog.finish()
    assert dialog.report['resultado']['recommended']>=4
    assert dialog.save_button.isEnabled() and not dialog.running
    assert 'senha' not in __import__('json').dumps(dialog.report).lower()
    dialog.close();shiboken6.delete(dialog)
    other=PCAnalysisDialog(owner);other.cancel()
    assert not other.running and other.report is None
    other.close();shiboken6.delete(other);shiboken6.delete(owner)


def test_warning_when_delivery_drops_above_measured_recommendation():
    warning=PressureWarning()
    sample=dict(channels=9,recommended=8,cpu=50,system_cpu=65,available_mb=4000,rss_mb=400,fps_ratio=.6,stable=True)
    assert not warning.update(sample,0)
    assert not warning.update(sample,3)
    assert warning.update(sample,6)
