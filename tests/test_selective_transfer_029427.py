"""Inventory transfer uses local SQLite only; no DVR or network calls."""
import json
import pytest
from artin_sentinel.db import Database
from artin_sentinel.config_portability import export_configuration,import_configuration

@pytest.fixture
def databases(tmp_path):
    a=Database(tmp_path/'a.db');b=Database(tmp_path/'b.db')
    yield a,b
    a.close();b.close()

def add(db,site,ip,serial='',name='DVR',manufacturer='Intelbras',model='MHDX'):
    now='2026-10-20T12:00:00+00:00'
    cursor=db.conn.execute('INSERT INTO devices(site_id,name,ip,manufacturer,model,serial,kind,provider,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
        (site,name,ip,manufacturer,model,serial,'dvr','intelbras','unknown',now,now))
    did=cursor.lastrowid
    db.conn.execute('INSERT INTO recorder_channels(device_id,channel_no,name,alias,preferred_stream,updated_at) VALUES(?,?,?,?,?,?)',(did,1,'CAM 1','Portão','sub',now))
    return did

def test_export_selected_devices_and_fields_omits_credentials(databases):
    a,b=databases;sid=a.add_site('Casa');one=add(a,sid,'192.0.2.1','SERIAL-ONE');two=add(a,sid,'192.0.2.2','SERIAL-TWO')
    a.conn.execute('UPDATE devices SET metadata_json=?,rtsp_url=?,credential_username=? WHERE id=?',(json.dumps({'password':'PRIVATE','token':'PRIVATE'}),'rtsp://u:PRIVATE@192.0.2.1/live','PRIVATE',one))
    data=export_configuration(a,device_ids={one},include_channels=True,include_names=False,include_streams=False,include_layouts=False)
    devices=data['sites'][0]['devices']
    assert len(devices)==1 and devices[0]['serial']=='SERIAL-ONE'
    assert devices[0]['name']=='192.0.2.1' and devices[0]['channels'][0]['alias']==''
    assert devices[0]['channels'][0]['preferred_stream']=='auto'
    assert 'PRIVATE' not in json.dumps(data) and 'rtsp://' not in json.dumps(data)

def test_serial_match_across_sites_is_skipped_and_existing_channels_untouched(databases):
    a,b=databases;src=a.add_site('Origem');dest=b.add_site('Destino')
    add(a,src,'192.0.2.2','SERIAL-ONE');existing=add(b,dest,'192.0.2.9','SERIAL-ONE',name='Preservado')
    before=[tuple(r) for r in b.conn.execute('SELECT * FROM devices')];channels=[tuple(r) for r in b.conn.execute('SELECT * FROM recorder_channels')]
    site_count=len(b.list_sites());payload=export_configuration(a)
    from artin_sentinel.config_portability import preview_configuration
    preview=preview_configuration(b,payload)
    assert preview['counts']['existing']==1 and preview['counts']['new']==0
    assert import_configuration(b,payload)['devices']==0
    assert [tuple(r) for r in b.conn.execute('SELECT * FROM devices')]==before
    assert [tuple(r) for r in b.conn.execute('SELECT * FROM recorder_channels')]==channels
    assert len(b.list_sites())==site_count

def test_ip_collision_with_different_serial_is_conflict_but_new_device_imports(databases):
    a,b=databases;s1=a.add_site('Casa');s2=b.add_site('Casa')
    add(a,s1,'192.0.2.1','OTHER-SERIAL');add(a,s1,'192.0.2.2','NEW-SERIAL')
    existing=add(b,s2,'192.0.2.1','DEST-SERIAL',name='Preservado')
    from artin_sentinel.config_portability import preview_configuration
    data=export_configuration(a);before=b.get_device(existing)['name']
    preview=preview_configuration(b,data)
    assert preview['counts']=={'new':1,'existing':0,'conflict':1}
    result=import_configuration(b,data)
    assert result['devices']==1 and b.get_device(existing)['name']==before
    assert import_configuration(b,data)['devices']==0

def test_preview_and_invalid_input_never_write(databases):
    a,b=databases;sid=a.add_site('Casa');add(a,sid,'192.0.2.1','SERIAL-ONE')
    data=export_configuration(a)
    from artin_sentinel.config_portability import preview_configuration
    before='\n'.join(b.conn.iterdump());preview_configuration(b,data)
    assert '\n'.join(b.conn.iterdump())==before
    data['sites'][0]['devices'][0]['port']=99999
    with pytest.raises(ValueError):import_configuration(b,data)
    assert '\n'.join(b.conn.iterdump())==before

def test_existing_device_does_not_receive_new_channel_or_layout(databases):
    a,b=databases;s1=a.add_site('Casa');s2=b.add_site('Casa')
    add(a,s1,'192.0.2.1');did=add(b,s2,'192.0.2.1',name='Destino')
    data=export_configuration(a);data['sites'][0]['devices'][0]['channels'].append(dict(channel_no=2,name='Extra',alias='',preferred_stream='main'))
    before='\n'.join(b.conn.iterdump());result=import_configuration(b,data)
    assert result['devices']==result['channels']==0
    assert '\n'.join(b.conn.iterdump())==before

def test_legacy_format_read_and_repeat_import_are_safe(databases):
    a,b=databases;sid=a.add_site('Casa');add(a,sid,'192.0.2.1')
    payload=export_configuration(a);payload['format']='artin-sentinel-portable-v1'
    for dev in payload['sites'][0]['devices']:dev.pop('serial');dev.pop('connection')
    assert import_configuration(b,payload)['devices']==1
    assert import_configuration(b,payload)['devices']==0

def test_preview_signature_rejects_inventory_change_without_partial_writes(databases):
    from artin_sentinel.config_portability import preview_configuration
    a,b=databases;sid=a.add_site('Casa');add(a,sid,'192.0.2.1','NEW-SERIAL')
    payload=export_configuration(a);preview=preview_configuration(b,payload)
    b.add_site('Outro');before='\n'.join(b.conn.iterdump())
    with pytest.raises(ValueError,match='inventário mudou'):
        import_configuration(b,payload,expected_signature=preview['signature'])
    assert '\n'.join(b.conn.iterdump())==before

def test_layout_references_only_selected_new_equipment(databases):
    a,b=databases;sid=a.add_site('Casa');one=add(a,sid,'192.0.2.1','ONE-SERIAL');two=add(a,sid,'192.0.2.2','TWO-SERIAL')
    channels={d:a.list_recorder_channels(d)[0]['id'] for d in (one,two)}
    a.save_live_workspace(sid,4,[dict(type='channel',device_id=d,channel_id=channels[d]) for d in (one,two)])
    payload=export_configuration(a,device_ids={two},include_layouts=True)
    result=import_configuration(b,payload)
    target=b.conn.execute("SELECT id FROM sites WHERE name='Casa'").fetchone()[0]
    slots=b.load_live_workspace(target)['slots']
    assert result['devices']==1 and result['layouts']==1 and not slots[0] and slots[1]['type']=='channel'
    assert b.get_device(slots[1]['device_id'])['serial']=='TWO-SERIAL'

def test_duplicate_serials_in_file_are_conflicts_not_randomly_selected(databases):
    from artin_sentinel.config_portability import preview_configuration
    a,b=databases;sid=a.add_site('Casa');add(a,sid,'192.0.2.1','SAME-SERIAL');add(a,sid,'192.0.2.2','SAME-SERIAL')
    payload=export_configuration(a);assert preview_configuration(b,payload)['counts']['conflict']==2
    assert import_configuration(b,payload)['devices']==0

def test_hikvision_hilook_and_cloud_identity_remain_unverified(databases):
    a,b=databases;sid=a.add_site('Mallet')
    hik=add(a,sid,'192.0.2.10','HIK-SERIAL',manufacturer='Hikvision',model='DS-TEST')
    look=add(a,sid,'192.0.2.11','LOOK-SERIAL',manufacturer='HiLook',model='DVR-TEST')
    cloud=add(a,sid,'CLOUD-SERIAL','CLOUD-SERIAL')
    a.conn.execute('UPDATE devices SET metadata_json=? WHERE id=?',(json.dumps(dict(connection_mode='intelbras_cloud_bridge',wine_managed=True,bridge_port=37777,cloud_serial='CLOUD-SERIAL',password='PRIVATE')),cloud))
    payload=export_configuration(a);assert 'PRIVATE' not in json.dumps(payload)
    assert import_configuration(b,payload)['devices']==3
    rows=b.conn.execute('SELECT * FROM devices').fetchall()
    assert {r['manufacturer'] for r in rows}=={'Hikvision','HiLook','Intelbras'}
    assert all(r['status']=='unknown' and not r['credential_saved'] for r in rows)
    imported=next(r for r in rows if r['serial']=='CLOUD-SERIAL')
    assert json.loads(imported['metadata_json'])['wine_managed'] is True
    assert json.loads(imported['metadata_json'])['identity_source']=='portable_import_unverified'


def test_write_failure_rolls_back_every_imported_row(databases):
    a,b=databases;sid=a.add_site('Casa');add(a,sid,'192.0.2.1','ONE-SERIAL');add(a,sid,'192.0.2.2','TWO-SERIAL')
    b.conn.execute("CREATE TRIGGER reject_second BEFORE INSERT ON devices WHEN NEW.ip='192.0.2.2' BEGIN SELECT RAISE(ABORT,'synthetic rejection'); END")
    before='\n'.join(b.conn.iterdump())
    import sqlite3
    with pytest.raises(sqlite3.IntegrityError):import_configuration(b,export_configuration(a))
    assert '\n'.join(b.conn.iterdump())==before

def test_same_address_without_serial_in_different_sites_remains_distinct(databases):
    a,b=databases;src=a.add_site('Loja A');dst=b.add_site('Loja B')
    add(a,src,'192.0.2.1');add(b,dst,'192.0.2.1')
    assert import_configuration(b,export_configuration(a))['devices']==1

def test_ports_and_https_are_reconstructed_without_serialising_urls(databases):
    a,b=databases;sid=a.add_site('Casa');did=add(a,sid,'192.0.2.1','PORT-SERIAL')
    a.conn.execute('UPDATE devices SET web_url=?,metadata_json=? WHERE id=?',('https://192.0.2.1:8443/login',json.dumps(dict(netsdk_port=37777,recorder_rtsp_port=1554,password='PRIVATE')),did))
    payload=export_configuration(a);raw=json.dumps(payload)
    assert 'https://' not in raw and 'PRIVATE' not in raw
    import_configuration(b,payload)
    row=b.conn.execute("SELECT * FROM devices WHERE serial='PORT-SERIAL'").fetchone()
    assert row['web_url']=='https://192.0.2.1:8443'
    assert json.loads(row['metadata_json'])['recorder_rtsp_port']==1554

@pytest.mark.parametrize('field,value',[('mac','02:12:34:56:78:90'),('uuid','12345678-1234-1234-1234-123456789abc')])
def test_identity_without_serial_uses_mac_or_uuid_across_sites(databases,field,value):
    from artin_sentinel.config_portability import preview_configuration
    a,b=databases;s1=a.add_site('Origem');s2=b.add_site('Destino')
    one=add(a,s1,'192.0.2.1');two=add(b,s2,'192.0.2.99')
    a.conn.execute(f'UPDATE devices SET {field}=? WHERE id=?',(value,one))
    b.conn.execute(f'UPDATE devices SET {field}=? WHERE id=?',(value,two))
    payload=export_configuration(a)
    assert payload['sites'][0]['devices'][0][field]
    assert preview_configuration(b,payload)['counts']['existing']==1
    assert import_configuration(b,payload)['devices']==0

def test_stream_preferences_are_excluded_from_layout_slots_too(databases):
    a,b=databases;sid=a.add_site('Casa');did=add(a,sid,'192.0.2.1','ONE-SERIAL');cid=a.list_recorder_channels(did)[0]['id']
    a.save_live_workspace(sid,4,[dict(type='channel',device_id=did,channel_id=cid,forced_stream='sub')])
    payload=export_configuration(a,include_streams=False,include_layouts=True)
    assert payload['sites'][0]['workspace']['slots'][0]['forced_stream']==''

def test_selected_subset_is_applied_and_archived_site_is_not_restored(databases):
    from artin_sentinel.config_portability import preview_configuration
    a,b=databases;sid=a.add_site('Casa');add(a,sid,'192.0.2.1','ONE-SERIAL');add(a,sid,'192.0.2.2','TWO-SERIAL')
    payload=export_configuration(a);preview=preview_configuration(b,payload)
    selected={tuple(preview['rows'][0]['key'])}
    assert import_configuration(b,payload,selected_keys=selected,expected_signature=preview['signature'])['devices']==1
    target=b.conn.execute("SELECT id FROM sites WHERE name='Casa'").fetchone()[0]
    b.conn.execute('UPDATE sites SET archived=1 WHERE id=?',(target,))
    before='\n'.join(b.conn.iterdump())
    assert import_configuration(b,payload)['devices']==0
    assert '\n'.join(b.conn.iterdump())==before
