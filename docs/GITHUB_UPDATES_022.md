# Atualizações via GitHub — fundação 0.2.2

A 0.2.2 adiciona `artin_sentinel/updater.py` com:

- normalização/comparação de versões;
- consulta à release pública mais recente de um repositório `owner/repo`;
- descoberta de asset ZIP e checksum quando publicados.

Não há atualização silenciosa. Download, verificação SHA-256 e instalação assistida serão uma etapa posterior, sempre com consentimento explícito.

Dados do usuário ficam fora da árvore de instalação: SQLite/Sites/layouts em `~/.local/share/artin-sentinel` e senhas no keyring quando disponível.
