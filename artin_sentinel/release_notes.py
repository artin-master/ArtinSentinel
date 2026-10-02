RELEASE_TITLE = "Acesso Web confirmado e gestão de equipamentos"
RELEASE_NOTES = [
    "A descoberta confirma serviços HTTP/HTTPS e conserva o histórico de confirmações e falhas por endpoint.",
    "A ação Web exige confirmação real e permite escolher entre serviços; URLs abertas não levam credenciais.",
    "Configuração → Equipamentos separa visualmente equipamentos cadastrados e dispositivos localizados.",
    "Canais e Excluir da descoberta ficam agrupados no menu Mais.",
    "O cadastro manual preserva os campos em caso de erro e o contador informa os equipamentos visíveis pelo filtro.",
    "A suíte automatizada e a verificação de consistência da versão acompanham a release.",
]
CHANGELOG_TEXT = """Artin Sentinel 0.2.92 — Acesso Web confirmado e gestão de equipamentos

- HTTP e HTTPS são sondados separadamente; as confirmações e falhas ficam no histórico do endpoint.
- A interface Web só abre após resposta HTTP confirmada. Serviços múltiplos podem ser selecionados sem levar credenciais na URL.
- A tela Equipamentos separa os cadastrados dos dispositivos descobertos, com ações agrupadas junto de cada tabela.
- O formulário manual conserva os valores em erros de validação; o contador do filtro informa quantos equipamentos estão visíveis.
- A suíte automatizada e a verificação das fontes oficiais de versão acompanham a release.
"""
