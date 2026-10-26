RELEASE_TITLE = "Importação assistida + Hikvision Playback"
RELEASE_NOTES = [
    "Equipamentos importados podem ser administrados em uma visão Todos os Sites sem alterar o Site ativo do monitoramento.",
    "A importação retoma cadastros existentes sem duplicação e inicia configuração assistida quando faltam credencial ou canais validados.",
    "Após confirmar a credencial, o fluxo normal do provider inicia a leitura/validação dos canais.",
    "Busca Hikvision ISAPI recebe hardening de XML, ResponseStatus, track e playbackURI; HCNetSDK opcional da 0.2.94.32 é preservado.",
    "Intelbras/NetSDK, Cloud, Live View, reprodução e exportação existentes permanecem na base 0.2.94.32.",
    "Candidata requer validação física dos DVRs importados e da gravação Hikvision antes de publicação estável.",
]
CHANGELOG_TEXT = """Artin Sentinel 0.2.94.33 — Importação Assistida + Hikvision Playback

• Configuração → Equipamentos oferece visão Todos os Sites sem misturar o Site operacional.
• Importações novas ou já existentes são retomadas pelo cadastro original, sem duplicação.
• Equipamentos incompletos entram em configuração pós-importação para credencial e validação de canais.
• A leitura normal por provider é reutilizada; Canais / Stream continua disponível para ajustes posteriores.
• Hikvision ISAPI reforçado com conteúdo de vídeo/metadata explícitos, ResponseStatus sanitizado, track estrito e playbackURI sem credenciais embutidas.
• HCNetSDK Hikvision opcional/isolado da .32 permanece intacto.
• Intelbras/NetSDK, Cloud e demais providers permanecem intactos.
• Validação física ainda necessária antes de promover esta candidata a estável.
"""
