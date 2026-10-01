# Artin Sentinel 0.1.6 — MHDX RTSP Compatibility

## Contexto de campo

O Intelbras **MHDX 1004** em `192.168.15.254` foi detectado com HTTP, RTSP/554 e serviço 37777. A 0.1.5 corrigiu o SIGSEGV do fluxo de credencial e confirmou que o gravador responde ao RTSP, mas o cliente RTSP interno ainda não concluiu a autenticação.

## Evidência pública usada

A Intelbras documenta para a linha MHDX/gravadores o padrão:

`rtsp://usuario:senha@ip:porta/cam/realmonitor?channel=N&subtype=S`

onde `subtype=0` representa o stream principal e `subtype=1` o stream extra. Há também registro específico de MHDX 1004 usando o mesmo formato em suporte oficial da Intelbras.

## Hipóteses tratadas na 0.1.6

1. firmware exige `CSeq` crescente;
2. firmware não aceita parâmetro `algorithm=MD5` se ele não veio no desafio;
3. variação de `digest-uri` entre URI absoluta e path/query;
4. firmware anuncia `qop` mas exige forma Digest legada;
5. cliente interno ainda diverge do comportamento tolerado por VLC/libavformat;
6. URL reconhecida, mas canal/substream inexistente.

## Estratégia

A 0.1.6 mantém tentativas limitadas, somente leitura e determinísticas. Primeiro usa `DESCRIBE` pelo cliente interno. Se houver resposta de autenticação não confirmada e `ffprobe` estiver disponível, executa uma segunda validação independente por libavformat. Nenhum segredo é escrito nos logs.

## Segurança

- nenhuma senha é persistida;
- logs não incluem usuário/senha nem URL com credenciais;
- nenhuma configuração é escrita no gravador;
- o fallback externo é opcional;
- timeouts permanecem limitados e a leitura pode ser cancelada.
