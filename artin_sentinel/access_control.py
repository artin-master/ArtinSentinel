"""Optional local application roles. These are not Linux user accounts."""
from functools import wraps
import json,os,tempfile,time
from pathlib import Path
from .app_auth import AppAuth

PERMISSION_LABELS={
    'device_add':'Cadastrar equipamentos',
    'device_edit':'Editar, arquivar e excluir equipamentos',
    'playback':'Pesquisar e reproduzir gravações',
    'record':'Gravar vídeo ao vivo',
    'export':'Exportar vídeos e salvar fotos',
    'recorded_audio':'Ouvir áudio das gravações',
    'export_audio':'Exportar gravações com áudio',
}
DEFAULT_PERMISSIONS={key:key=='playback' for key in PERMISSION_LABELS}

class AccessControl:
    def __init__(self,directory,*,now=time.monotonic):
        self.path=Path(directory)/'access-control.json'
        self.admin_auth=AppAuth(Path(directory)/'admin-access.json')
        self._admin=False;self._attempts=0;self._blocked_until=0;self.now=now
        self.enabled=False;self.permissions=dict(DEFAULT_PERMISSIONS);self.error=False
        if self.path.exists():
            try:
                data=json.loads(self.path.read_text())
                if data.get('version')!=1 or type(data.get('enabled')) is not bool or not isinstance(data.get('permissions'),dict):raise ValueError('policy')
                self.enabled=data['enabled']
                self.permissions={key:data['permissions'].get(key,False) for key in PERMISSION_LABELS}
                if any(type(v) is not bool for v in self.permissions.values()):raise ValueError('permission')
            except (OSError,ValueError,TypeError,AttributeError):
                self.enabled=True;self.permissions={key:False for key in PERMISSION_LABELS};self.error=True

    @property
    def is_admin(self):return self._admin

    def allows(self,capability):
        if capability not in (*PERMISSION_LABELS,'admin'):return False
        return not self.enabled or self.is_admin or (capability!='admin' and self.permissions.get(capability,False))

    def set_admin_password(self,password):
        if (self.admin_auth.configured or self.enabled) and not self.is_admin:raise PermissionError('Acesso administrativo necessário.')
        if not isinstance(password,str) or not 8<=len(password)<=1024:raise ValueError('Use de 8 a 1024 caracteres.')
        self.admin_auth.set_password(password)

    def unlock_admin(self,password):
        if self.now()<self._blocked_until:return False
        if isinstance(password,str) and len(password)<=1024 and self.admin_auth.verify(password):
            self._admin=True;self._attempts=0;return True
        self._attempts+=1
        if self._attempts>=5:self._blocked_until=self.now()+60;self._attempts=0
        return False

    def lock(self):self._admin=False

    def configure(self,enabled,permissions):
        if not self.is_admin:raise PermissionError('Acesso administrativo necessário.')
        if type(enabled) is not bool or set(permissions)!=set(PERMISSION_LABELS) or any(type(v) is not bool for v in permissions.values()):raise ValueError('Permissões inválidas.')
        self.path.parent.mkdir(parents=True,exist_ok=True)
        fd,temporary=tempfile.mkstemp(prefix='.permissions-',dir=self.path.parent)
        try:
            with os.fdopen(fd,'w') as stream:
                json.dump(dict(version=1,enabled=enabled,permissions=permissions),stream)
                stream.flush();os.fsync(stream.fileno())
            os.chmod(temporary,0o600);os.replace(temporary,self.path)
        finally:
            if os.path.exists(temporary):os.unlink(temporary)
        self.enabled=enabled;self.permissions=dict(permissions);self.error=False


def authorize(owner,capability,*,notify=True):
    control=getattr(owner,'access_control',None)
    if control is None or control.allows(capability):return True
    if notify:
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.information(owner,'Acesso restrito','Esta função não está liberada para o operador.\nUse o acesso de administrador para continuar.')
    return False


def requires_permission(capability):
    def decorate(function):
        @wraps(function)
        def guarded(self,*args,**kwargs):
            if not authorize(self,capability,notify=not kwargs.get('silent',False)):return None
            return function(self,*args,**kwargs)
        return guarded
    return decorate
