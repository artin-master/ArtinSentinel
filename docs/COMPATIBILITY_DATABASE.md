# Matriz de compatibilidade

| Fabricante | Modelo | Firmware | Descoberta | RTSP | Canais | Live View | Gravação | HDD | Estado |
|---|---|---|---|---|---|---|---|---|---|
| Intelbras | **MHDX 1004** | A coletar | **Detectado em campo** por HTTP/RTSP/37777 | **Validado em campo**; autenticação + ffprobe OK | **4/4 validados**, H.264 1280×720 | Implementado na 0.1.7; validação física pendente | Não validado | Não validado | Provider prioritário |
| Intelbras | Mibo iMX C | iMX C | **Validada em campo** | **RTSP direto + ONVIF** | 1 | **Live View + áudio de escuta validados (AAC)** | **MIC PEND — Intelbras-1 candidato** | N/A | Campo + documentação fabricante |
| Intelbras | **VIPC 1230 D G2** | 2.860.00IB000.0.T (DoC ONVIF consultada) | Perfil documentado/AKDB | Main/Sub `/cam/realmonitor` | 1 câmera / 2 streams | Pendente de campo | N/A | N/A | ONVIF S/T; sem PTZ/áudio no perfil documentado |
| IT-Blue | **Speed Dome X3-WE2Q** | V5.02.R02.000A06CD (família) | **Identificada em campo**; LAN disponível | **1 lente RTSP já abriu em campo**; 0.2.12 testa índices 0/1/2 | Até 3 visões observadas; só persiste streams distintos | **1 lente validada**; demais em investigação | N/A | N/A | PTZ/áudio/tracking observados |
| Hikvision | **DS-7216HGHI-F1** | A coletar | Perfil AKDB + roteamento DVR dedicado | `/Streaming/Channels/{canal}01/02`; validação física pendente | 16 analógicos + até 2 IP | Pendente de campo | Pendente | Pendente | 0.2.14: ISAPI read-only + roteamento DVR; campo pendente |
| JFL | A validar | A validar | Pendente | Pendente | Pendente | Pendente | Pendente | Pendente | Campo |
| Haiz | A validar | A validar | Pendente | Pendente | Pendente | Pendente | Pendente | Pendente | Campo |
| Positivo | A validar | A validar | Pendente | Pendente | Pendente | Pendente | Pendente | Pendente | Campo |
| Aitek | **SIGMA-SEG6050BP / H2-52PGX** | 2.2.0-20250916SG (observado) | **Identificada em campo** | **Main/Sub validados** | 1 | **Live View validado em HEVC**; áudio em revalidação 0.2.12 | N/A | N/A | Campo |

## Perfis documentados adicionados na 0.2.13

- **Hikvision DS-7216HGHI-F1**: perfil dedicado com 16 entradas analógicas, até 2 entradas IP, dual stream e família RTSP Hikvision. O suporte físico no ambiente do usuário ainda precisa ser validado.
- **Intelbras VIPC 1230 D G2**: perfil dedicado com 2 streams, RTSP Intelbras/Dahua e ONVIF S/T. A declaração ONVIF do modelo informa ausência de PTZ e áudio, por isso esses controles não são oferecidos automaticamente.

## Evidência MHDX 1004

No teste físico da 0.1.6, o Sentinel identificou quatro canais e o `ffprobe/libavformat` confirmou vídeo H.264 1280×720 em todos. A 0.1.7 usa esses endpoints para o Live View e passa a derivar/persistir URLs main/substream por canal.

## Regra de evidência

O Sentinel não promove uma função a “compatível” apenas por documentação genérica ou semelhança de protocolo. Os estados distinguem **documentado**, **detectado**, **testado** e **validado em campo**.


## Evidência IT-Blue X3-WE2Q

A câmera disponível na LAN é uma Speed Dome comercializada como IT-Blue. O aplicativo do equipamento reporta `X3-WE2Q` e firmware da família `V5.02.R02.000A06CD`. Foram observados PTZ, tracking, detecção humana, alarme sonoro/luminoso, áudio full duplex e três visões. Em campo, uma das três visões já abriu no Sentinel. A 0.2.12 testa os índices RTSP 0/1/2 e usa hash de frame para descartar aliases; se o firmware expuser apenas a lente principal por RTSP, as demais ficam pendentes de provider XM/DVRIP/34567 em vez de serem criadas como canais falsos.

A segunda Speed Dome IT-Blue observada (`IPC_GK7202V300_LPG-G5-WQ`) está disponível somente via cloud no ambiente atual e não recebe URL LAN inferida.


## Evolução 0.2.14

A AKDB passa a registrar tipo canônico como dado estrutural. O DS-7216HGHI-F1 é roteado como DVR antes da seleção de protocolo; uma consulta ISAPI GET somente leitura pode confirmar autenticação separadamente da validação RTSP. O estado continua **pendente de campo** até o hardware real confirmar enumeração e Live View.
