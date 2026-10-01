# AKDB Sync + Field Learning — 0.2.43

## Modelo de dados

A AKDB mantém três conceitos separados:

1. **Core oficial** — conhecimento publicado e versionado.
2. **Conhecimento/evidência local** — observações do computador atual.
3. **Pending / Field Reports** — candidatos sanitizados aguardando submissão/revisão.

Um relatório de campo nunca promove uma identidade automaticamente para conhecimento homologado.

## Sincronização oficial

O Sentinel lê um manifesto `artin-akdb-manifest-v1`, baixa o bundle indicado, valida SHA-256 e calcula o delta antes de aplicar. O operador vê quantas identidades e extensões são novas ou editadas. O bundle oficial é aplicado sem apagar relatórios/evidências locais.

Fonte padrão:

`https://raw.githubusercontent.com/artin-master/ArtinUpdates/main/akdb/stable.json`

## Field Learning

Cada `field_report` novo entra em `submission_queue`. O envio é opcional. Quando habilitado, o Sentinel envia os candidatos para uma caixa de entrada GitHub configurada. O token é armazenado no keyring e deve ser fine-grained, limitado ao repositório de inbox.

Antes do upload, o payload passa por uma segunda sanitização defensiva. São removidos/redigidos IPs, MACs, seriais/UUIDs, usuários, senhas/tokens/credenciais e URLs completas.

## Segurança

O app não transforma submissões em Core oficial. A caixa de entrada é somente uma área de candidatos. A homologação/publicação da AKDB continua sendo uma etapa separada de revisão.
