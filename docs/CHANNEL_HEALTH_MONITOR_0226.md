# Artin Sentinel 0.2.26 — Channel Health Monitor

A 0.2.26 adiciona supervisão operacional de canais sem transformar o Live View em um decodificador permanente de todos os streams.

## Objetivos

- Detectar quando um canal previamente conhecido deixa de fornecer vídeo ou quando o próprio gravador informa perda de sinal.
- Diferenciar a queda do gravador da falha de uma câmera/canal individual.
- Exibir, quando o provider fornecer, o IP, porta e protocolo da câmera IP configurada dentro do DVR/NVR.
- Registrar perda e recuperação no histórico de Eventos.
- Evitar falsos positivos durante reconexões curtas.

## Estratégia

O monitor principal continua em 30 s. Depois que o gravador é confirmado online, o Sentinel executa uma verificação de canais somente leitura.

- Hikvision: ISAPI `Video/inputs/channels` e `InputProxy/channels/status` são a fonte preferencial.
- Outros providers: somente as URLs RTSP já conhecidas são verificadas com DESCRIBE leve; o monitor periódico não executa ffprobe nem procura novas URLs.
- Uma primeira falha coloca o canal em `CONFIRMANDO`; a segunda falha consecutiva promove para `SEM SINAL` ou `OFFLINE` e gera evento.
- Recuperação para `OK` é aplicada imediatamente e gera evento de restauração quando havia falha confirmada.

## Estados

- `OK`: canal/sinal confirmado.
- `CONFIRMANDO`: primeira falha; ainda sem alerta.
- `SEM SINAL`: típico de entrada física/analógica ou rota de vídeo ausente com gravador online.
- `OFFLINE`: câmera IP/proxy reportada offline pelo gravador ou sem mídia na rota conhecida.
- `SEM ESTADO`: ainda não verificado ou sem credencial/telemetria suficiente.

## Endpoint IP

O banco passa a manter `source_ip`, `source_port` e `source_protocol` por canal. Esses campos representam o endpoint que o gravador informou para uma câmera IP/proxy; não são inferidos a partir do IP da estação Sentinel.

Na 0.2.26 essa informação é homologada para Hikvision/ISAPI. Providers Intelbras/Dahua continuam conservadores até que a leitura nativa do cadastro remoto seja validada em hardware real.

## Regra de agrupamento

Se o DVR/NVR estiver offline, o Sentinel não gera um alerta por canal durante aquela mesma verificação. O evento do gravador representa a falha agregada; os estados por canal permanecem como último estado conhecido até o equipamento voltar.
