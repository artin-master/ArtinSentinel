# Artin Sentinel 0.2.8 — Aitek RTSP Compatibility

## Objetivo

A câmera Aitek de campo responde em HTTP/80 e RTSP/554, porém não entregou imagem no Live View com os candidatos anteriores. Esta revisão amplia a compatibilidade sem assumir uma URL como correta: todos os caminhos são tratados como candidatos e só são persistidos quando `ffprobe/libavformat` confirma um stream de vídeo decodificável.

## Estratégia

1. Usar ONVIF GetDeviceInformation/GetProfiles/GetStreamUri quando o firmware responder.
2. Se ONVIF não fornecer mídia utilizável, testar candidatos Aitek/XM limitados e somente leitura.
3. Priorizar TCP; se não houver vídeo e a falha for compatível com transporte, tentar UDP.
4. Persistir somente Main/Sub efetivamente validados.
5. Nunca gravar a senha na AKDB, SQLite ou logs. Templates usam `{username}` e `{password}` e são materializados apenas em memória.

## Famílias candidatas

- raiz RTSP `rtsp://host:554/`;
- `/ch01/0` e `/ch01/1`;
- `/ch0/stream0` e `/ch0/stream1`;
- variantes XM/XMEye com `user`, `password`, `channel`, `stream` e sufixo `.sdp`, com ou sem `real_stream`.

Esses caminhos não significam compatibilidade confirmada com todo equipamento Aitek. O estado só deve subir para validado em campo após confirmação física por modelo/firmware.
