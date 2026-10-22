import sys,time,threading
from concurrent.futures import ThreadPoolExecutor
import pytest
from artin_sentinel.intelbras_wine import WineTunnelManager
from test_intelbras_wine_manager import fake_process


def manager_for(tmp_path,seconds):
    script=fake_process(tmp_path)
    return WineTunnelManager(root=tmp_path/'runtime',prefix=tmp_path/'prefix',idle_timeout=seconds,
        command_factory=lambda report,stop,port:[sys.executable,str(script),str(report),str(stop),'ready','35551'])


def test_default_grace_is_three_minutes_and_shutdown_reaps_warm_process(tmp_path):
    script=fake_process(tmp_path)
    manager=WineTunnelManager(root=tmp_path/'runtime',prefix=tmp_path/'prefix',
        command_factory=lambda report,stop,port:[sys.executable,str(script),str(report),str(stop),'ready','35551'])
    try:
        assert manager.idle_timeout==180
        lease=manager.acquire('TEST-SERIAL',37777);lease.release()
        assert lease.entry.alive()
        manager.shutdown()
        assert lease.entry.process.poll()==0 and not manager.entries
    finally:manager.shutdown()


def test_reacquire_reuses_pid_and_active_lease_cancels_old_expiry(tmp_path):
    manager=manager_for(tmp_path,.3)
    try:
        a=manager.acquire('TEST-SERIAL',37777);a.release();time.sleep(.12)
        b=manager.acquire('TEST-SERIAL',37777)
        assert b.entry is a.entry
        time.sleep(.35)
        assert b.entry.alive()
        b.release();b.release()
        assert b.entry.done.wait(2)
        assert b.entry.process.poll()==0 and not manager.entries
    finally:manager.shutdown()


def test_concurrent_warm_consumers_share_one_process(tmp_path):
    manager=manager_for(tmp_path,.3)
    try:
        a=manager.acquire('TEST-SERIAL',37777);a.release();barrier=threading.Barrier(2)
        def get():barrier.wait();return manager.acquire('TEST-SERIAL',37777)
        with ThreadPoolExecutor(2) as pool:
            jobs=[pool.submit(get) for _ in range(2)];b,c=[job.result(timeout=3) for job in jobs]
        assert b.entry is c.entry is a.entry and a.entry.refs==2
        b.release();time.sleep(.35);assert c.entry.alive()
        c.release();assert c.entry.done.wait(2)
    finally:manager.shutdown()


def test_expired_tunnel_finishes_before_replacement_starts(tmp_path):
    script=fake_process(tmp_path)
    text=script.read_text().replace("report.write_text(json.dumps({'phase':'finished'", "time.sleep(.2)\nreport.write_text(json.dumps({'phase':'finished'")
    script.write_text(text)
    previous=[]
    def command(report,stop,port):
        if previous:assert previous[0].poll() is not None
        return [sys.executable,str(script),str(report),str(stop),'ready','35551']
    manager=WineTunnelManager(root=tmp_path/'runtime',prefix=tmp_path/'prefix',idle_timeout=.1,command_factory=command)
    try:
        a=manager.acquire('TEST-SERIAL',37777);previous.append(a.entry.process);a.release()
        assert a.entry.stop_requested.wait(2)
        b=manager.acquire('TEST-SERIAL',37777)
        assert b.entry is not a.entry and a.entry.process.poll()==0
        b.release()
    finally:manager.shutdown()


def test_dead_warm_child_is_replaced_on_next_explicit_access(tmp_path):
    manager=manager_for(tmp_path,180)
    try:
        a=manager.acquire('TEST-SERIAL',37777);a.release()
        a.entry.process.terminate();a.entry.process.wait(timeout=2)
        b=manager.acquire('TEST-SERIAL',37777)
        assert b.entry is not a.entry and b.entry.alive()
        b.release()
    finally:manager.shutdown()
