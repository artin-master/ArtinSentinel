"""Import the operator's private Linux payload, keeping an existing SDK untouched."""
import hashlib
import json
from pathlib import Path
import sys
import zipfile


def install(bundle,target):
    bundle,target=Path(bundle),Path(target)
    if (target/'libdhnetsdk.so').is_file():
        return 'NetSDK existente preservado.'
    with zipfile.ZipFile(bundle) as z:
        manifest=json.loads(z.read('manifest.json'))
        payload={}
        for item in manifest:
            name=item['name']
            if Path(name).name!=name or not name.endswith('.so'):
                raise ValueError('Nome inválido no pacote privado do SDK.')
            raw=z.read(name)
            if hashlib.sha256(raw).hexdigest()!=item['sha256']:
                raise ValueError('Hash divergente no pacote privado do SDK.')
            if raw[:5]!=b'\x7fELF\x02':raise ValueError('SDK precisa ser ELF64.')
            payload[name]=raw
        if 'libdhnetsdk.so' not in payload:raise ValueError('SDK principal ausente.')
    target.mkdir(parents=True,exist_ok=True)
    for name,raw in payload.items():
        dst=target/name;pending=target/(name+'.pending')
        pending.write_bytes(raw);pending.chmod(0o755);pending.replace(dst)
    return f'NetSDK Linux64: {len(payload)} bibliotecas importadas.'


if __name__=='__main__':
    print(install(sys.argv[1],sys.argv[2]))
