# Artin Sentinel 0.2.94.33 — Importação Assistida + Hikvision Playback

Base: 0.2.94.32.

## Importação assistida

A transferência entre computadores continua sem copiar senhas, tokens ou URLs autenticadas. Depois da importação, o Sentinel resolve novamente os registros representados no arquivo e retoma o próprio cadastro existente, sem duplicação.

A aba Configuração → Equipamentos passa a oferecer uma visão administrativa **Todos os Sites**. Ela não muda o Site ativo do monitoramento, da Saúde ou dos layouts. Isso permite localizar imediatamente um DVR importado de outro Site, informar a credencial e validar canais.

Equipamentos importados que ainda não possuem credencial salva ou rota de mídia validada entram numa fila pós-importação. O Sentinel seleciona cada cadastro existente e abre o fluxo normal de acesso somente leitura. Ao confirmar a credencial, a leitura de canais é iniciada pelo provider já selecionado. O botão Canais / Stream permanece disponível para manutenção posterior.

## Hikvision

O caminho existente da 0.2.94.32 é preservado:
- ISAPI/RTSP;
- HCNetSDK opcional e isolado;
- pesquisa de gravações;
- reprodução;
- exportação SDK/MP4.

A busca ISAPI recebe hardening adicional: conteúdo de vídeo e metadata de gravação declarados explicitamente, tratamento de ResponseStatus, validação estrita do track retornado, rejeição de credencial embutida no playbackURI e preservação do tamanho informado quando presente.

## Intelbras

Nenhum caminho Intelbras/NetSDK foi substituído por esta alteração. Cloud, NetSDK, reprodução, exportação e demais providers permanecem na base 0.2.94.32.

## Validação de campo

A candidata deve ser validada em:
1. importação de DVR já existente da Mallet sem duplicação;
2. visibilidade em Equipamentos → Todos os Sites;
3. credencial pós-importação;
4. leitura automática de canais;
5. Hikvision ISAPI/HCNetSDK conforme configuração do DVR;
6. busca de um intervalo gravado conhecido;
7. reprodução e exportação MP4.
