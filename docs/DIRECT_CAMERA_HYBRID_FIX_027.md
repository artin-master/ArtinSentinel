# Direct Camera + Hybrid Channel Fix — 0.2.7

## Problema de campo

Na 0.2.6, Aitek e MiboCam podiam ser cadastradas e aparecer na árvore, mas o Live View permanecia em `Conectando`/`Sem vídeo`. Além disso, o Canal 05 IP do MHDX 1004 continuava ausente.

## Mudança de regra

Um `DESCRIBE` RTSP bem-sucedido deixa de ser evidência suficiente para câmera IP direta. Quando `ffprobe` está disponível, o Sentinel exige confirmação de um stream de vídeo decodificável antes de persistir o canal como disponível.

Fluxo:

1. ONVIF GetDeviceInformation;
2. ONVIF GetProfiles/GetStreamUri;
3. validação de cada URI com ffprobe/libavformat;
4. fallback por padrões AKDB/provider;
5. persistência somente do perfil validado;
6. Live View.

## Compatibilidade adicionada

### Intelbras Mibo/iMX

São testados, de forma somente leitura, padrões `cam/realmonitor`, variante ONVIF query e alguns caminhos legados. O equipamento continua podendo exigir habilitação de ONVIF/RTSP no app do fabricante.

### Aitek

A AKDB tenta famílias de caminhos observadas em firmwares diferentes (`ch01`, `ch0/stream`, `snl/live`). Há também template XM com placeholders de credencial. O segredo nunca é persistido dentro da URL.

### IT-Blue/XM

O provider pode testar template RTSP XM com placeholders de credencial e `/11`/`/12`, sempre exigindo validação antes de salvar.

## MHDX 1004 — Canal 05

A varredura Intelbras já testava canais além de 4. A 0.2.7 corrige o ffprobe usado como segunda implementação RTSP para não forçar `rw_timeout`, removendo uma causa que poderia impedir a confirmação de canais extras que dependessem do fallback libavformat.

## Identidade detectada x manual

A base passa a manter campos detectados separados de fabricante/modelo/tipo corrigidos manualmente. O operador pode nomear/corrigir o equipamento sem contaminar a evidência automática usada pela AKDB.
