"""Brand guides onboarding; capabilities and explicit channel maps remain required."""
def recommendation(brand,kind,runtime_available=False):
    brand=str(brand).strip().casefold()
    recorder=kind in {'dvr','nvr','xvr'}
    hik=brand in {'hikvision','hilook'}
    intel=brand in {'intelbras','dahua'}
    provider='hikvision' if hik else 'intelbras' if intel else ''
    sdk='hikvision' if hik and recorder else 'intelbras' if intel and recorder else ''
    detail=('Hikvision SDK local disponível; canais precisam de mapeamento confirmado.' if runtime_available else 'Hikvision: importe o SDK em Componentes e SDKs para preparar o acesso local.') if sdk=='hikvision' else ('Acesso Intelbras compatível; recursos dependem do modelo e do teste.' if provider=='intelbras' else 'Acesso ONVIF/RTSP; confirmar compatibilidade no teste de canais.')
    return dict(provider=provider,sdk=sdk,detail=detail)
