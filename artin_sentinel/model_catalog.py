"""Read-only catalog: a general profile validation never validates every feature."""
from .akdb_runtime import effective_core_records
from .akdb import profile_by_stable_id,capability_map

FEATURES={'live':'Vídeo ao vivo','substream':'Substream','audio':'Escuta de áudio',
          'talkback':'Áudio bidirecional','ptz':'PTZ','search':'Pesquisa de gravações',
          'playback':'Reprodução gravada','speed':'Velocidade gravada','export':'Exportação de vídeo'}

def catalog_models():
    models=[]
    for core in effective_core_records():
        profile=profile_by_stable_id(core.stable_id)
        caps=capability_map(profile_key=profile.key) if profile else {}
        features={key:{'label':label,'status':'pending','detail':'Sem validação individual registrada.',
                       'firmware':'Não individualizado','source':'—'} for key,label in FEATURES.items()}
        evidence='; '.join(core.provenance) or 'Catálogo AKDB'
        def mark(key,status,detail):
            features[key].update(status=status,detail=detail,source=evidence)
        if profile:
            if 'rtsp' in core.protocols:mark('live','known','Vídeo RTSP descrito no perfil; validar acesso neste aparelho.')
            if profile.stream_count>1:mark('substream','known','Múltiplos streams descritos no perfil; confirmar neste equipamento.')
            if profile.audio_mode=='none':mark('audio','unsupported-profile','Perfil não indica escuta de áudio.')
            elif profile.audio_mode not in {'unknown','none'}:mark('audio','known','Escuta descrita no perfil; confirmar canal e firmware.')
            if profile.talkback_validation in {'homologated','field-validated'}:mark('talkback','validated','Validação específica de retorno de áudio registrada no perfil.')
            elif profile.talkback_protocol:mark('talkback','known','Protocolo candidato: '+profile.talkback_protocol)
            if 'confirmed' in profile.ptz_mode:mark('ptz','validated','Controle específico confirmado no perfil: '+profile.ptz_mode)
            elif profile.ptz_mode=='none':mark('ptz','unsupported-profile','Perfil sem PTZ.')
            elif profile.ptz_mode!='unknown':mark('ptz','known','Modo descrito: '+profile.ptz_mode)
        if any('listen-audio-field-validated'==v for v in core.capabilities):
            mark('audio','validated','Escuta validada em campo; firmware não individualizado na base.')
        models.append({'id':core.stable_id,'key':profile.key if profile else '',
            'manufacturer':core.manufacturer,'model':core.model or core.family or 'Família sem modelo individualizado',
            'type':core.canonical_type,'variant':core.variant,'family':core.family,
            'general_status':core.validation_status,'revision':core.revision,'source':evidence,
            'domains':core.domains,'features':features,'protocols':list(core.protocols),
            'ports':list(profile.ports_any) if profile else [],'notes':list(profile.notes) if profile else [],
            'negative_knowledge':list(core.negative_knowledge),'capabilities':list(core.capabilities),
            'provider':profile.provider if profile else 'generic','caps':caps})
    return sorted(models,key=lambda r:(r['manufacturer'].casefold(),r['type'],r['model'].casefold()))

STATUS_LABELS={'pending':'Pendente','known':'Conhecido • confirmar',
               'validated':'Validação registrada','unsupported-profile':'Não indicado no perfil'}
