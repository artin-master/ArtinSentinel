RELEASE_TITLE = "Hikvision Playback/Export Hardening"
RELEASE_NOTES = [
    "Busca de gravações Hikvision mantém o mesmo searchID ao paginar resultados ISAPI, melhorando a compatibilidade com firmwares antigos.",
    "Paginação 0/40/80 possui limite, deduplicação e proteção contra páginas repetidas.",
    "Erros 401/403/404 da busca Hikvision são diferenciados sem expor credenciais ou URLs autenticadas.",
    "Playback/exportação continuam usando o playbackURI devolvido pelo gravador, reroteado para o endpoint cadastrado e sem aceitar credenciais embutidas.",
    "Intelbras, ONVIF genérico e demais providers permanecem no comportamento da 0.2.94.1; validação física Hikvision ainda é necessária.",
]
CHANGELOG_TEXT = """Artin Sentinel 0.2.95 — Hikvision Playback/Export Hardening

- Corrige a paginação da busca Hikvision ISAPI para reutilizar um único searchID durante a consulta e avançar apenas a posição dos resultados.
- Adiciona deduplicação e proteção contra páginas repetidas, preservando o limite de busca por canal.
- Diferencia autenticação negada, endpoint indisponível, resposta inválida e indisponibilidade de rede com mensagens sanitizadas.
- Valida o playbackURI retornado pelo Hikvision, rejeita credenciais embutidas, preserva o tamanho informado e reroteia o RTSP para o endpoint cadastrado.
- O fluxo existente de reprodução/exportação MP4 é preservado; Intelbras e demais providers não foram alterados.
- Esta é uma candidata para validação física no Hikvision antes de publicação estável.
"""
