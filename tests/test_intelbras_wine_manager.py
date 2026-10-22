"""Lifecycle checks use real disposable processes, not the vendor network."""
import json
import os
from pathlib import Path
import sys
import threading
import time
import zipfile
import pytest


def fake_process(tmp_path, scenario='ready'):
    script=tmp_path/'helper.py'
    script.write_text('''import json,sys,time
from pathlib import Path
report,stop,scenario,port=Path(sys.argv[1]),Path(sys.argv[2]),sys.argv[3],int(sys.argv[4])
# Consume private request as the original console helper does.
sys.stdin.readline();sys.stdin.readline();sys.stdin.readline()
if scenario=='hang':
 while True:time.sleep(.1)
if scenario=='crash':raise SystemExit(7)
report.write_text(json.dumps({'phase':'tunnel_hold','result':'tunnel_ready_observed','local_port':port}))
while not stop.exists():time.sleep(.02)
report.write_text(json.dumps({'phase':'finished','result':'tunnel_closed','cleanup_returned':True}))
''')
    return script


def test_two_channels_share_one_tunnel_and_last_release_stops_it(tmp_path):
    from artin_sentinel.intelbras_wine import WineTunnelManager
    script=fake_process(tmp_path)
    manager=WineTunnelManager(idle_timeout=0,root=tmp_path/'runtime',prefix=tmp_path/'prefix',
        command_factory=lambda report,stop,port:[sys.executable,str(script),str(report),str(stop),'ready','35551'])
    a=manager.acquire('TEST-SERIAL',37777)
    b=manager.acquire('TEST-SERIAL',37777)
    assert a.port==b.port==35551
    assert a.entry is b.entry
    process=a.entry.process
    a.release();assert process.poll() is None
    b.release();assert process.poll()==0
    assert b.entry.report['cleanup_returned'] is True
    manager.shutdown()


def test_other_serial_has_its_own_process(tmp_path):
    from artin_sentinel.intelbras_wine import WineTunnelManager
    script=fake_process(tmp_path)
    manager=WineTunnelManager(root=tmp_path/'runtime',prefix=tmp_path/'prefix',
        command_factory=lambda report,stop,port:[sys.executable,str(script),str(report),str(stop),'ready','35552'])
    a=manager.acquire('TEST-SERIAL-A',37777);b=manager.acquire('TEST-SERIAL-B',37777)
    assert a.entry.process.pid!=b.entry.process.pid
    manager.shutdown()
    assert a.entry.process.poll()==0 and b.entry.process.poll()==0
    with pytest.raises(ValueError):manager.acquire('TEST-SERIAL',37777)
    a.release();b.release()


def test_cancel_pending_acquisition_has_no_orphan(tmp_path):
    from artin_sentinel.intelbras_wine import WineTunnelManager
    script=fake_process(tmp_path)
    processes=[]
    manager=WineTunnelManager(root=tmp_path/'runtime',prefix=tmp_path/'prefix',startup_timeout=.4,
        command_factory=lambda report,stop,port:[sys.executable,str(script),str(report),str(stop),'hang','35553'])
    cancel=threading.Event();cancel.set()
    with pytest.raises(ValueError,match='cancelad'):manager.acquire('TEST-SERIAL',37777,cancel_event=cancel)
    assert not manager.entries
    start=time.monotonic()
    with pytest.raises(ValueError):manager.acquire('TEST-SERIAL',37777)
    assert time.monotonic()-start<5
    assert not manager.entries
    manager.shutdown()


def test_failed_child_is_not_accepted_as_ready(tmp_path):
    from artin_sentinel.intelbras_wine import WineTunnelManager
    script=fake_process(tmp_path)
    manager=WineTunnelManager(root=tmp_path/'runtime',prefix=tmp_path/'prefix',startup_timeout=.5,
        command_factory=lambda report,stop,port:[sys.executable,str(script),str(report),str(stop),'crash','35554'])
    with pytest.raises(ValueError):manager.acquire('TEST-SERIAL',37777)
    assert not manager.entries
    manager.shutdown()


def test_zip_rejects_changed_or_recording_service_module_before_install(tmp_path):
    from artin_sentinel.intelbras_wine import extract_verified
    archive=tmp_path/'wrong.zip'
    with zipfile.ZipFile(archive,'w') as z:z.writestr('SIMNext/Local Recording Service/SIMNext.P2PSDK.dll',b'bad')
    with pytest.raises(ValueError):extract_verified(archive,tmp_path/'out')
    assert not (tmp_path/'out').exists()


def test_concurrent_consumers_coalesce_and_cancel_one_keeps_other(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from artin_sentinel.intelbras_wine import WineTunnelManager
    script=fake_process(tmp_path)
    barrier=threading.Barrier(2)
    manager=WineTunnelManager(idle_timeout=0,root=tmp_path/'runtime',prefix=tmp_path/'prefix',
        command_factory=lambda report,stop,port:[sys.executable,str(script),str(report),str(stop),'ready','35551'])
    def get():
        barrier.wait();return manager.acquire('TEST-SERIAL',37777)
    with ThreadPoolExecutor(2) as pool:
        jobs=[pool.submit(get) for _ in range(2)]
        a,b=[j.result(timeout=5) for j in jobs]
    assert a.entry is b.entry
    a.release();assert b.entry.alive()
    b.release();assert b.entry.process.poll()==0
    manager.shutdown()


def test_cancel_while_starting_terminates_owned_process(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from artin_sentinel.intelbras_wine import WineTunnelManager
    script=fake_process(tmp_path)
    cancel=threading.Event()
    manager=WineTunnelManager(root=tmp_path/'runtime',prefix=tmp_path/'prefix',close_timeout=.1,
        command_factory=lambda report,stop,port:[sys.executable,str(script),str(report),str(stop),'hang','35551'])
    with ThreadPoolExecutor(1) as pool:
        pending=pool.submit(manager.acquire,'TEST-SERIAL',37777,cancel_event=cancel)
        deadline=time.monotonic()+3
        while not manager.entries and time.monotonic()<deadline:time.sleep(.01)
        entry=next(iter(manager.entries.values()))
        cancel.set()
        with pytest.raises(ValueError,match='cancelad'):pending.result(timeout=4)
    assert entry.process.poll() is not None
    assert not manager.entries
    manager.shutdown()


def test_cancel_compilation_keeps_installed_runtime_and_reaps_compiler(tmp_path,monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from artin_sentinel import intelbras_wine as module
    prefix=tmp_path/'prefix';prefix.mkdir()
    root=tmp_path/'runtime';root.mkdir();(root/'Bridge.exe').write_bytes(b'previous-runtime')
    def extract(_archive,destination):Path(destination).mkdir()
    monkeypatch.setattr(module,'extract_verified',extract)
    monkeypatch.setattr(module.shutil,'which',lambda command:'/usr/bin/'+command)
    original=module.subprocess.Popen;children=[];started=threading.Event()
    def compiler(_command,**kwargs):
        child=original([sys.executable,'-c','import time;time.sleep(99)'],**kwargs)
        children.append(child);started.set();return child
    monkeypatch.setattr(module.subprocess,'Popen',compiler)
    manager=module.WineTunnelManager(root=root,prefix=prefix)
    cancel=threading.Event()
    with ThreadPoolExecutor(1) as pool:
        job=pool.submit(manager.prepare,tmp_path/'placeholder.zip',cancel_event=cancel)
        assert started.wait(3);cancel.set()
        with pytest.raises(ValueError,match='cancelad'):job.result(timeout=4)
    assert all(child.poll() is not None for child in children)
    assert (root/'Bridge.exe').read_bytes()==b'previous-runtime'
    assert not (root/'installed.json').exists()
    manager.shutdown()
