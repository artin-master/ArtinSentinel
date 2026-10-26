"""Selective inventory transfer. Credentials and media URLs never enter the file."""
from __future__ import annotations
from collections import Counter,defaultdict
from datetime import datetime,timezone
import hashlib,json,re
from urllib.parse import urlparse
from uuid import UUID
from . import __version__
from .remote_access import validate_recorder_host

FORMAT='artin-sentinel-portable-v2'
LEGACY_FORMAT='artin-sentinel-portable-v1'
MODES={'local','private_remote','site_connector','intelbras_cloud_bridge'}


def _text(value,limit=256):
    if not isinstance(value,str) or len(value)>limit or any(ord(c)<32 for c in value):
        raise ValueError('Texto inválido ou longo demais no arquivo portátil.')
    return value.strip()


def _integer(value,minimum,maximum):
    if isinstance(value,str) and re.fullmatch(r'[0-9]{1,5}',value):value=int(value)
    if type(value) is not int or not minimum<=value<=maximum:raise ValueError('Número ou porta inválida no arquivo portátil.')
    return value


def _serial(value):
    value=_text(value,64).upper()
    if value in {'UNKNOWN','UNCONFIRMED','NONE','N/A'} or not re.fullmatch(r'[A-Z0-9_-]{4,64}',value) or set(value)<={'0','-','_'}:return ''
    return value


def _mac(value):
    if not isinstance(value,str):return ''
    compact=re.sub(r'[:. -]','',value).upper()
    if not re.fullmatch(r'[A-F0-9]{12}',compact) or compact in ('000000000000','FFFFFFFFFFFF') or int(compact[:2],16)&1:return ''
    return ':'.join(compact[i:i+2] for i in range(0,12,2))


def _uuid(value):
    if not isinstance(value,str) or len(value)>100:return ''
    try:
        parsed=UUID(value.strip().lower().removeprefix('urn:uuid:').removeprefix('uuid:'))
        return str(parsed) if parsed.int else ''
    except ValueError:return ''


def _vendor(value):return value.strip().casefold()

def _choice(value,choices,default):
    return value if isinstance(value,str) and value in choices else default


def _metadata(device):
    try:
        result=json.loads(device['metadata_json'] or '{}')
        return result if isinstance(result,dict) else {}
    except (KeyError,TypeError,ValueError):return {}


def _export_connection(device):
    meta=_metadata(device);mode=meta.get('connection_mode','local')
    if not isinstance(mode,str) or mode not in MODES:mode='local'
    result={'mode':mode,'protocol':meta.get('recorder_protocol','')}
    if not isinstance(result['protocol'],str) or result['protocol'] not in {'','intelbras','hikvision'}:result['protocol']=''
    for key in ('recorder_rtsp_port','netsdk_port'):
        value=meta.get(key)
        if type(value) is int and 1<=value<=65535:result[key]=value
    if mode!='intelbras_cloud_bridge':
        try:
            web=urlparse(device['web_url'] or '')
            if web.scheme in ('http','https') and not web.username and not web.password and web.hostname and web.hostname.casefold()==device['ip'].casefold():
                result['web_scheme']=web.scheme
                result['web_port']=web.port or (443 if web.scheme=='https' else 80)
        except ValueError:pass
    if mode=='intelbras_cloud_bridge':
        result['wine_managed']=bool(meta.get('wine_managed'))
        result['bridge_port']=meta.get('bridge_port',37777 if result['wine_managed'] else 55162)
    return result


def _slots(db,slots,selected,include_streams=True):
    result=[]
    for slot in slots:
        if not isinstance(slot,dict) or slot.get('type')!='channel':result.append({});continue
        device=db.get_device(int(slot.get('device_id') or 0));channel=db.get_recorder_channel(int(slot.get('channel_id') or 0))
        if not device or device['id'] not in selected or not channel or channel['device_id']!=device['id']:
            result.append({});continue
        result.append(dict(ip=device['ip'],channel_no=int(channel['channel_no']),
            forced_stream=_choice(slot.get('forced_stream'),{'main','sub'},'') if include_streams else '',
            display_mode=_choice(slot.get('display_mode'),{'fit','fill','original'},'fit')))
    return result


def export_configuration(db,*,device_ids=None,include_channels=True,include_names=True,include_streams=True,include_layouts=True):
    selected=None if device_ids is None else {int(x) for x in device_ids}
    sites=[]
    for site in db.list_sites(include_archived=False):
        devices=[];included=set()
        for device in db.list_devices(int(site['id'])):
            if selected is not None and device['id'] not in selected:continue
            included.add(device['id'])
            channels=[dict(channel_no=int(ch['channel_no']),name=ch['name'] if include_names else f"Canal {ch['channel_no']:02d}",
                alias=ch['alias'] if include_names else '',preferred_stream=ch['preferred_stream'] if include_streams else 'auto')
                for ch in db.list_recorder_channels(int(device['id']))] if include_channels else []
            meta=_metadata(device)
            devices.append({key:device[key] for key in ('ip','port','manufacturer','model','kind','provider')}
                |dict(name=device['name'] if include_names else device['ip'],serial=_serial(device['serial'] or meta.get('cloud_serial','')),
                      mac=_mac(device['mac']),uuid=_uuid(device['uuid']),channels=channels,connection=_export_connection(device)))
        if not devices:continue
        workspace=db.load_live_workspace(int(site['id'])) if include_layouts and include_channels else None
        windows=db.list_live_windows(int(site['id'])) if include_layouts and include_channels else []
        sites.append(dict(name=site['name'],description=site['description'],devices=devices,
            workspace=dict(grid_count=workspace['grid_count'],slots=_slots(db,workspace['slots'],included,include_streams=include_streams)) if workspace else None,
            windows=[dict(key=row['window_key'],title=row['title'] if include_names else 'Monitoramento',
                grid_count=row['grid_count'],slots=_slots(db,row['slots'],included,include_streams=include_streams)) for row in windows]))
    payload=dict(format=FORMAT,source_version=__version__,exported_at=datetime.now(timezone.utc).isoformat(),
        notice='Sem senhas, tokens ou URLs de vídeo. Informe credenciais e valide os canais no destino.',
        options=dict(channels=bool(include_channels),names=bool(include_names),streams=bool(include_streams and include_channels),layouts=bool(include_layouts and include_channels)),sites=sites)
    _normalise(payload)
    return payload


def _connection(value):
    if not isinstance(value,dict):raise ValueError('Dados de conexão inválidos.')
    mode=value.get('mode','local');protocol=value.get('protocol','')
    if not isinstance(mode,str) or not isinstance(protocol,str) or mode not in MODES or protocol not in {'','intelbras','hikvision'}:raise ValueError('Modo de conexão inválido.')
    result=dict(connection_mode=mode,recorder_protocol=protocol,identity_source='portable_import_unverified')
    if 'web_scheme' in value:
        if value['web_scheme'] not in ('http','https'):raise ValueError('Protocolo Web inválido.')
        result['web_scheme']=value['web_scheme']
    for key in ('recorder_rtsp_port','netsdk_port','web_port'):
        if key in value:result[key]=_integer(value[key],1,65535)
    if mode=='intelbras_cloud_bridge':
        if type(value.get('wine_managed',False)) is not bool:raise ValueError('Ponte inválida.')
        result['wine_managed']=value.get('wine_managed',False)
        result['bridge_port']=_integer(value.get('bridge_port',37777 if result['wine_managed'] else 55162),1,65535)
    return result


def _layout(value,*,window=False):
    if not isinstance(value,dict):raise ValueError('Layout inválido.')
    count=_integer(value.get('grid_count'),1,144);slots=value.get('slots')
    if not isinstance(slots,list) or len(slots)>144:raise ValueError('Posições inválidas.')
    result=dict(grid_count=count,slots=[])
    for slot in slots:
        if not slot:result['slots'].append({});continue
        if not isinstance(slot,dict):raise ValueError('Posição inválida.')
        result['slots'].append(dict(ip=_text(slot.get('ip')),channel_no=_integer(slot.get('channel_no'),1,256),
            forced_stream=_choice(slot.get('forced_stream'),{'main','sub'},''),
            display_mode=_choice(slot.get('display_mode'),{'fit','fill','original'},'fit')))
    if window:result.update(key=_text(value.get('key',''),128),title=_text(value.get('title','Monitoramento')))
    return result


def _normalise(payload):
    if not isinstance(payload,dict) or not isinstance(payload.get('format'),str) or payload.get('format') not in {FORMAT,LEGACY_FORMAT}:raise ValueError('Formato de configuração não reconhecido.')
    sites=payload.get('sites')
    if not isinstance(sites,list) or len(sites)>100:raise ValueError('Lista de Sites inválida.')
    result=[];names=set();total=0
    for site in sites:
        if not isinstance(site,dict):raise ValueError('Site inválido.')
        name=_text(site.get('name'))
        if not name or name.casefold() in names:raise ValueError('Site sem nome ou repetido no arquivo.')
        names.add(name.casefold());devices=site.get('devices');windows=site.get('windows',[])
        if not isinstance(devices,list) or len(devices)>2000 or not isinstance(windows,list) or len(windows)>30:raise ValueError('Inventário ou janelas inválidas.')
        total+=len(devices)
        if total>5000:raise ValueError('O arquivo excede 5.000 equipamentos.')
        item=dict(name=name,description=_text(site.get('description',''),1024),devices=[],
            workspace=_layout(site['workspace']) if site.get('workspace') is not None else None,
            windows=[_layout(w,window=True) for w in windows])
        for dev in devices:
            if not isinstance(dev,dict):raise ValueError('Equipamento inválido.')
            serial=_serial(dev.get('serial',''));connection=_connection(dev.get('connection',{}));ip=_text(dev.get('ip'),253)
            if connection['connection_mode']=='intelbras_cloud_bridge':
                if not serial or ip.upper()!=serial:raise ValueError('Serial Cloud ausente ou divergente.')
                ip=serial;connection['cloud_serial']=serial
            else:ip=validate_recorder_host(ip)
            port=dev.get('port')
            if port is not None:port=_integer(port,1,65535)
            kind=_text(dev.get('kind','unknown'),32);provider=_text(dev.get('provider','generic'),64)
            if kind not in {'camera','dvr','nvr','xvr','unknown'} or not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}',provider):raise ValueError('Tipo ou protocolo inválido.')
            channels=dev.get('channels',[])
            if not isinstance(channels,list) or len(channels)>256:raise ValueError('Canais inválidos.')
            clean=[];numbers=set()
            for ch in channels:
                if not isinstance(ch,dict):raise ValueError('Canal inválido.')
                no=_integer(ch.get('channel_no'),1,256)
                if no in numbers:raise ValueError('Canal repetido no equipamento.')
                numbers.add(no)
                clean.append(dict(channel_no=no,name=_text(ch.get('name','')),alias=_text(ch.get('alias','')),
                    preferred_stream=_choice(ch.get('preferred_stream'),{'auto','main','sub'},'auto')))
            item['devices'].append(dict(ip=ip,port=port,name=_text(dev.get('name','')) or ip,
                manufacturer=_text(dev.get('manufacturer','')),model=_text(dev.get('model','')),serial=serial,
                mac=_mac(dev.get('mac','')),uuid=_uuid(dev.get('uuid','')),kind=kind,provider=provider,connection=connection,channels=clean))
        result.append(item)
    return result


def _endpoint(device):
    try:return validate_recorder_host(device['ip'])
    except ValueError:return str(device['ip']).strip().upper()


def _plan(db,sites):
    existing=[dict(row) for row in db.list_devices(include_archived=True)]
    target_sites=[dict(row) for row in db.list_sites(include_archived=True)]
    keys=('serial','uuid','mac')
    identities={key:Counter(d[key] for site in sites for d in site['devices'] if d[key]) for key in keys}
    index={key:defaultdict(list) for key in keys};address_index=defaultdict(list);site_index=defaultdict(list)
    for d in existing:
        d['_serial']=_serial(d['serial'] or _metadata(d).get('cloud_serial',''))
        d['_uuid']=_uuid(d['uuid']);d['_mac']=_mac(d['mac'])
        for key in keys:
            if d['_'+key]:index[key][d['_'+key]].append(d)
        address_index[(d['site_id'],_endpoint(d).casefold())].append(d)
    for site in target_sites:site_index[site['name'].casefold()].append(site)
    rows=[]
    for si,site in enumerate(sites):
        matches=site_index[site['name'].casefold()]
        sid=matches[0]['id'] if len(matches)==1 else None
        endpoints=Counter(d['ip'].casefold() for d in site['devices'])
        for di,dev in enumerate(site['devices']):
            status='new';reason='Equipamento novo';target_device_id=None
            matched={d['id']:d for key in keys if dev[key] for d in index[key][dev[key]]}
            same_address=address_index[(sid,dev['ip'].casefold())] if sid is not None else []
            if len(matches)>1 or (matches and matches[0]['archived']):status='conflict';reason='Site ambíguo ou arquivado no destino'
            elif endpoints[dev['ip'].casefold()]>1 or any(dev[k] and identities[k][dev[k]]>1 for k in keys):
                status='conflict';reason='Identidade repetida no arquivo; selecione um único cadastro na origem'
            elif same_address and any(dev[k] and d['_'+k] and dev[k]!=d['_'+k] for d in same_address for k in keys):
                status='conflict';reason='Endereço ocupado por outra identidade no destino'
            elif matched:
                incompatible=any((d['manufacturer'] and dev['manufacturer'] and _vendor(d['manufacturer'])!=_vendor(dev['manufacturer']))
                    or any(dev[k] and d['_'+k] and dev[k]!=d['_'+k] for k in keys) for d in matched.values())
                status='conflict' if incompatible else 'existing'
                reason='Identificadores ou fabricante divergentes' if incompatible else 'Serial, UUID ou MAC já cadastrado; preservado'
                if status == 'existing':
                    target_device_id = int(sorted(matched)[0])
            elif same_address:
                old=same_address[0]
                different=(dev['port'] is not None and old['port'] is not None and dev['port']!=old['port']) or any(bool(dev[k] or old['_'+k]) and dev[k]!=old['_'+k] for k in keys) or any(old[k] and dev[k] and old[k].casefold()!=dev[k].casefold() for k in ('manufacturer','model'))
                status='conflict' if different else 'existing'
                reason='Endereço ocupado com identidade diferente ou incompleta' if different else 'Endereço já cadastrado neste Site; preservado'
                if status == 'existing':
                    target_device_id = int(old['id'])
            rows.append(dict(key=(si,di),site=site['name'],name=dev['name'],ip=dev['ip'],serial=dev['serial'],
                status=status,reason=reason,channels=len(dev['channels']),target_device_id=target_device_id))
    counts={key:sum(row['status']==key for row in rows) for key in ('new','existing','conflict')}
    snapshot=dict(sites=sites,rows=rows,target_devices=[(d['id'],d['site_id'],d['ip'],d['_serial'],d['_uuid'],d['_mac'],d['manufacturer'],d['model'],d['archived']) for d in existing],target_sites=[(s['id'],s['name'],s['archived']) for s in target_sites],
        layouts=[tuple(row) for row in db.conn.execute('SELECT site_id FROM live_workspaces')],
        windows=[tuple(row) for row in db.conn.execute('SELECT site_id,window_key FROM live_windows')])
    digest=hashlib.sha256(json.dumps(snapshot,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    return dict(rows=rows,counts=counts,signature=digest)


def preview_configuration(db,payload):
    return _plan(db,_normalise(payload))


def _restore_slots(slots,channels):
    result=[]
    for slot in slots:
        ids=channels.get((slot['ip'].casefold(),slot['channel_no'])) if slot else None
        result.append(dict(type='channel',device_id=ids[0],channel_id=ids[1],
            forced_stream=slot.get('forced_stream',''),display_mode=slot.get('display_mode','fit')) if ids else {})
    return result


def import_configuration(db,payload,*,selected_keys=None,expected_signature=None):
    sites=_normalise(payload);counts=dict(sites=0,devices=0,channels=0,layouts=0)
    now=datetime.now(timezone.utc).isoformat()
    db.conn.execute('SAVEPOINT portable_import')
    try:
        preview=_plan(db,sites)
        if expected_signature is not None and expected_signature!=preview['signature']:raise ValueError('O inventário mudou. Abra novamente a prévia antes de importar.')
        eligible={tuple(row['key']) for row in preview['rows'] if row['status']=='new'}
        selected=eligible if selected_keys is None else set(selected_keys)
        if not selected<=eligible:raise ValueError('A seleção inclui equipamentos indisponíveis para importação.')
        for si,site in enumerate(sites):
            devices=[(di,d) for di,d in enumerate(site['devices']) if (si,di) in selected]
            if not devices:continue
            # Resolve with the same Unicode-aware rules as the preview.
            matches=[s for s in db.list_sites(include_archived=True) if s['name'].casefold()==site['name'].casefold()]
            if matches:sid=int(matches[0]['id'])
            else:
                sid=int(db.conn.execute('INSERT INTO sites(name,description,created_at) VALUES(?,?,?)',(site['name'],site['description'],now)).lastrowid);counts['sites']+=1
            ids={}
            for di,dev in devices:
                connection=dev['connection']
                scheme=connection.get('web_scheme','http');port=connection.get('web_port',443 if scheme=='https' else 80)
                web='' if connection['connection_mode']=='intelbras_cloud_bridge' else scheme+'://'+dev['ip']+(':'+str(port) if port!=(443 if scheme=='https' else 80) else '')
                did=int(db.conn.execute('''INSERT INTO devices(site_id,name,ip,port,manufacturer,model,serial,mac,uuid,kind,provider,status,web_url,metadata_json,canonical_type,created_at,updated_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',(sid,dev['name'],dev['ip'],dev['port'],dev['manufacturer'],dev['model'],dev['serial'],dev['mac'],dev['uuid'],dev['kind'],dev['provider'],'unknown',web,json.dumps(connection),dev['kind'],now,now)).lastrowid)
                counts['devices']+=1
                for ch in dev['channels']:
                    cid=int(db.conn.execute('INSERT INTO recorder_channels(device_id,channel_no,name,alias,preferred_stream,updated_at) VALUES(?,?,?,?,?,?)',
                        (did,ch['channel_no'],ch['name'],ch['alias'],ch['preferred_stream'],now)).lastrowid)
                    ids[(dev['ip'].casefold(),ch['channel_no'])]=(did,cid);counts['channels']+=1
            workspace=site['workspace']
            if workspace and not db.conn.execute('SELECT 1 FROM live_workspaces WHERE site_id=?',(sid,)).fetchone():
                slots=_restore_slots(workspace['slots'],ids)
                if any(slots):
                    db.conn.execute('INSERT INTO live_workspaces(site_id,grid_count,slots_json,updated_at) VALUES(?,?,?,?)',(sid,workspace['grid_count'],json.dumps(slots),now));counts['layouts']+=1
            for window in site['windows']:
                if not window['key'] or db.conn.execute('SELECT 1 FROM live_windows WHERE site_id=? AND window_key=?',(sid,window['key'])).fetchone():continue
                slots=_restore_slots(window['slots'],ids)
                if any(slots):
                    db.conn.execute('INSERT INTO live_windows(site_id,window_key,title,grid_count,slots_json,enabled,updated_at) VALUES(?,?,?,?,?,?,?)',
                        (sid,window['key'],window['title'],window['grid_count'],json.dumps(slots),1,now));counts['layouts']+=1
        db.conn.execute('RELEASE SAVEPOINT portable_import')
    except Exception:
        db.conn.execute('ROLLBACK TO SAVEPOINT portable_import');db.conn.execute('RELEASE SAVEPOINT portable_import');raise
    return counts
