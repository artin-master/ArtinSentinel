"""Authenticated local Intelbras SDK playback with device-side speed commands."""
from datetime import datetime
from urllib.parse import urlencode,urlparse,parse_qs
from .intelbras_cloud import IntelbrasCloudLiveSession,normalize_serial


def parse_local_route(url):
    parsed=urlparse(url);query=parse_qs(parsed.query,strict_parsing=True,keep_blank_values=True)
    if (parsed.scheme!='intelbras-sdk' or not parsed.hostname or parsed.username is not None or parsed.password is not None
            or parsed.fragment or set(query) not in ({'start','end'},{'start','end','serial'}) or any(len(v)!=1 for v in query.values())):
        raise ValueError('Rota local SDK inválida.')
    if any(c.isspace() for c in parsed.hostname) or any(c in parsed.hostname for c in '/@\\'):raise ValueError('Destino inválido.')
    port=parsed.port;channel=int(parsed.path.removeprefix('/'))
    if port is None or not 1<=port<=65535 or not 1<=channel<=256:raise ValueError('Porta/canal inválidos.')
    begin,end=(datetime.fromisoformat(query[key][0]) for key in ('start','end'))
    if begin.tzinfo is not None or end.tzinfo is not None or end<=begin or (end-begin).total_seconds()>86400:raise ValueError('Período local inválido.')
    serial=normalize_serial(query['serial'][0]) if query.get('serial') else ''
    return parsed.hostname,port,channel,serial


def local_playback_route(host,port,channel,start,end,serial=''):
    query=dict(start=start.isoformat(timespec='seconds'),end=end.isoformat(timespec='seconds'))
    if serial:query['serial']=normalize_serial(serial)
    authority=f'[{host}]' if ':' in host else host
    route=f'intelbras-sdk://{authority}:{int(port)}/{int(channel)}?{urlencode(query)}'
    parse_local_route(route)
    return route


class IntelbrasLocalPlaybackSession(IntelbrasCloudLiveSession):
    def __init__(self,*args,**kwargs):
        if not kwargs.get('playback'):raise ValueError('Transporte reservado para gravações locais.')
        super().__init__(*args,**kwargs)
        self.active_transport='NetSDK local'
        self.effective_playback_speed=1.0

    def _route(self,url):
        host,port,channel,serial=parse_local_route(url)
        return port,serial,channel

    def _sdk_options(self,url):
        host,port,channel,serial=parse_local_route(url)
        return dict(host=host,login_mode=0)


from .intelbras_cloud_audio import IntelbrasCloudAudioSession


class IntelbrasLocalPlaybackAudio(IntelbrasCloudAudioSession):
    def _route(self,url):
        host,port,channel,serial=parse_local_route(url)
        return port,serial,channel

    def _sdk_options(self,url):
        host,port,channel,serial=parse_local_route(url)
        return dict(host=host,login_mode=0)

    def _commands(self,*args):
        commands=super()._commands(*args)
        speed=self.playback_speed
        if speed!=1:
            stages=['atempo=0.5'] if speed==0.5 else ['atempo=2']*(int(speed).bit_length()-1)
            for backend,command in commands:
                index=command.index('-af')+1
                command[index]=','.join(stages+[command[index]])
        return commands
