# Validação de novos modelos — 0.2.4

A partir da 0.2.4, cada câmera/DVR/NVR novo deve ser tratado como uma amostra de campo e não como regra global de fabricante.

## Coleta mínima

- fabricante e modelo informados pelo operador;
- tipo real: câmera, DVR, NVR ou híbrido;
- portas/serviços encontrados;
- evidências HTTP/ONVIF/RTSP;
- provider escolhido e confiança;
- quantidade real de canais/sensores;
- Main/Substream quando confirmados;
- firmware quando o equipamento expuser a informação de forma somente leitura.

## Fluxo de teste

1. Descoberta sem correção manual.
2. Comparar identidade detectada com o equipamento real.
3. Corrigir identidade apenas depois de registrar o falso positivo, quando houver.
4. Testar RTSP/ONVIF e canais.
5. Exportar **Perfil AKDB**.
6. Promover conhecimento somente após revisão e, idealmente, repetição em outro aparelho/firmware.

## Equipamentos de referência atuais

- Intelbras MHDX 1004 — gravador híbrido, Live View validado em campo;
- Intelbras MiboCam — câmera IP detectada, compatibilidade direta ainda em expansão;
- IT-Blue — câmera IP identificada inicialmente por Web Viewer/serviços;
- Aitek — câmera IP de 1 canal; enumeração ampla de gravador é falso positivo conhecido;
- Hikvision — gravador detectado, provider e enumeração Hikvision em validação de campo;
- JFL — compatibilidade tipo Hikvision deve ser validada por modelo/firmware.
