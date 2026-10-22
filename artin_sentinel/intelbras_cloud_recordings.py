"""Read-only Cloud recording inventory; all native calls stay in the SDK child."""
from datetime import datetime
from urllib.parse import urlencode,urlparse,parse_qs
import time
import threading
from .intelbras_cloud import parse_bridge_route,_event_error
from .recording_search import Recording,SearchResult,RecordingSearchError


def playback_route(route,start,end):
    parse_bridge_route(route)
    if end<=start or (end-start).total_seconds()>86400:raise ValueError('Período inválido.')
    parsed=urlparse(route);query=parse_qs(parsed.query)
    query={key:values[0] for key,values in query.items() if key not in {'stream','start','end'}}
    query.update(start=start.isoformat(timespec='seconds'),end=end.isoformat(timespec='seconds'))
    return parsed._replace(query=urlencode(query)).geturl()


def search_cloud_recordings(route,username,password,channels,start,end,*,sdk_dir=None,cancel_event=None):
    from .intelbras_wine import wine_manager
    port,serial,_=parse_bridge_route(route)
    if not 1<=len(channels)<=4 or any(not 1<=int(n)<=256 for n in channels):raise RecordingSearchError('Selecione de um a quatro canais.')
    if start.tzinfo is not None or end.tzinfo is not None or end<=start or (end-start).total_seconds()>86400:raise RecordingSearchError('Período local inválido; limite de 24 horas.')
    lease=None;records=[];ignored=0;truncated=False;logins=0;reused=0
    try:
        if route.startswith('intelbras-wine:'):
            lease=wine_manager().acquire(serial,port,cancel_event=cancel_event);port=lease.port
        for channel in channels:
            if cancel_event is not None and cancel_event.is_set():raise RecordingSearchError('Busca cancelada.')
            query=dict(channel=int(channel),start=start.isoformat(),end=end.isoformat())
            from .playback_session_pool import playback_pool
            client=playback_pool().acquire(port,serial,username,password,sdk_dir=sdk_dir,
                                          channel=1,record_query=query,cancel_event=cancel_event or threading.Event())
            try:
                deadline=time.monotonic()+20
                while client.process.poll() is None:
                    client.poll_events()
                    if any(v['stage']=='session_idle' for v in client.events):break
                    if time.monotonic()>deadline or (cancel_event is not None and cancel_event.is_set()):raise RecordingSearchError('Busca interrompida ou prazo excedido.')
                    time.sleep(.02)
            finally:client.close()
            event=next((v for v in client.events if v.get('stage')=='recordings'),None)
            if client.process.returncode not in (0,None) or event is None:raise RecordingSearchError(_event_error(client.events))
            logins+=sum(v['stage']=='login_ok' for v in client.events)
            reused+=sum(v['stage']=='session_reused' for v in client.events)
            truncated=truncated or event.get('truncated',False)
            for value in event['items']:
                begin=datetime.fromisoformat(value['start']);finish=datetime.fromisoformat(value['end'])
                if value['channel']!=int(channel) or finish<=start or begin>=end or finish<=begin:
                    ignored+=1;continue
                chroute=urlparse(route)._replace(path='/'+str(channel)).geturl()
                records.append(Recording(int(channel),begin.strftime('%Y-%m-%d %H:%M:%S'),finish.strftime('%Y-%m-%d %H:%M:%S'),value['kind'],int(value['size']),playback_route(chroute,max(start,begin),min(end,finish))))
        return SearchResult(tuple(sorted(records,key=lambda v:(v.start,v.channel))),truncated,ignored,
                            diagnostics=(f'Pesquisa NetSDK • autenticações novas: {logins} • consultas com sessão reutilizada: {reused}',))
    except (ValueError,OSError) as exc:
        raise RecordingSearchError('Busca Cloud não concluída: '+type(exc).__name__) from None
    finally:
        if lease is not None:lease.release()
