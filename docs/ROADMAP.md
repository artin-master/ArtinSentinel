# Roadmap

## Base consolidada até 0.2.15

- configuração mais limpa e orientada a VMS;
- gerenciamento completo de Sites;
- exclusão segura com reatribuição de equipamentos;
- preserva Live View, mosaicos grandes, AKDB e Compatibility Capture.

## Próximos focos

- Recorder Intelligence aprofundada e identificação por modelo/firmware;
- playback/timeline multimarcas;
- health monitoring e correlação de eventos;
- Artin Bridge para acesso remoto;
- aceleração por hardware e escala de 100+ canais;
- Sentinel Intelligence em câmeras selecionadas.


### 0.2.6
- Hybrid channels + direct IP camera onboarding.
- Multi-monitor independent Live View windows.
- Individual and mosaic fullscreen.
- Preserve large-site scaling foundation.

## 0.2.7 — Direct Cameras + Hybrid Channel Fix

- validação real de câmera IP antes do Live View;
- identidade detectada separada da manual;
- Mibo/iMX, Aitek e IT-Blue com fallback RTSP orientado por AKDB;
- ffprobe RTSP compatível com o FFmpeg local;
- hardening do Canal 05 IP do MHDX;
- fluxo pós-update com novidades uma vez por versão.


## 0.2.8 — Aitek RTSP Compatibility

- provider hint seguro para identidade manual Aitek;
- candidatos RTSP Aitek/XM/XMEye adicionais, todos media-validados;
- ffprobe TCP → UDP para câmeras OEM que dependem de transporte;
- Live View direto com fallback de transporte;
- diagnóstico mais útil por assinatura RTSP sem expor credenciais.

## Diretriz 0.2.9 — local primeiro

Até estabilizar os providers locais multimarcas, priorizar ONVIF, RTSP, HTTP/HTTPS e AKDB em LAN. Intelbras Cloud, Hik-Connect/P2P e Artin Bridge permanecem posteriores.

## 0.2.10 — Live Audio + Media Diagnostics

- escuta RTSP por canal;
- capacidade de áudio persistente/AKDB;
- diagnóstico local de codecs;
- fundação segura de Push-to-Talk, sem transmissão antes de validação de backchannel.


### 0.2.11 — IT-Blue Speed Dome / PTZ
- X3-WE2Q: validar RTSP local, ONVIF PTZ, áudio/talkback e streams multi-view.
- Presets, patrulha, tracking e providers PTZ proprietários somente após validação do PTZ básico.


### 0.2.12 — Workspace Reorder + Audio Validation
- Live Audio valida a faixa antes de ativar e tenta Main/Sub; prioridade de campo para Aitek e MiboCam.
- Drag & drop entre tiles com persistência da nova ordem.
- Indicador visível do stream efetivamente usado.
- IT-Blue X3-WE2Q: tentativa bounded de três lentes RTSP com deduplicação; DVRIP/34567 permanece próximo passo se o firmware expuser só uma lente via RTSP.


### 0.2.13 — VMS Devices + Capability Mapping
- Equipamentos em workspace VMS com inventário filtrável e detalhes contextuais.
- Capability Mapping por modelo/perfil, sem projetar recursos de um modelo para todos do fabricante.
- PTZ refinado e habilitado conforme capacidade direta.
- Perfis dedicados Hikvision DS-7216HGHI-F1 e Intelbras VIPC 1230 D G2.
- Fundação de protocolos nativos read-only Hikvision ISAPI/service 8000 e Intelbras CGI.


### 0.2.14 — Device Intelligence + Field Stabilization
- Tipo de equipamento passa a ser conhecimento estrutural na AKDB.
- Override manual, AKDB e identidade detectada permanecem separados e possuem precedência operacional explícita.
- DVR/NVR Hikvision deixa de cair no scanner de câmera direta; ISAPI read-only auxilia diagnóstico de autenticação.
- Áudio ganha fallback local ffplay → Pulse/PipeWire → ALSA e validação de faixa em canais de gravadores.
- Console PTZ/Speed Dome é redesenhado para ergonomia de VMS.
- Prioridade de campo: estabilizar Hikvision, áudio e PTZ antes de novas funções grandes.


### 0.2.15 — Shared AKDB Foundation
- AKDB Core deixa de ser exclusiva do Sentinel e passa a usar IDs estáveis compartilháveis com NetLens e RescNow.
- Identidade central e extensões por domínio ficam separadas.
- SQLite compartilhado local usa WAL e revisão monotônica para impedir downgrade por apps antigos.
- Testes de campo entram como evidência candidata sanitizada, sem promoção automática para homologado.
- Bundle `artin-akdb-bundle-v1` formaliza o intercâmbio entre os aplicativos Artin.
- Sentinel permanece o primeiro consumidor; integração física com ANL/ARN será feita em seus ciclos próprios, preservando o mesmo core.

### 0.2.16–0.2.24 — consolidação de campo
- Live View/controle PTZ, identidade persistente, multi-endpoint, AKDB Intelligence, recuperação de compatibilidade, inventário Hikvision e canal híbrido MHDX foram progressivamente validados e endurecidos.
- O 5º canal IP/proxy do MHDX 1004 foi confirmado em campo via próprio DVR; áudio via recorder e tempo de abertura permanecem pontos de otimização.
- Talkback IT-Blue/Mibo permaneceu não homologado e deve ser tratado por provider, separado do áudio de escuta.

### 0.2.25 — Audio Stability + Recorder Route Intelligence
- volume dinâmico sem reiniciar/reconectar o RTSP quando PipeWire/PulseAudio oferece `pactl`;
- identificação do áudio ativo na status bar;
- probe de áudio via DVR para canal IP/proxy e persistência do resultado;
- isolamento completo dos canais MHDX 1–4 antes do Canal 5;
- cache do último Main/Sub válido para reduzir re-probes no canal híbrido;
- modos de enquadramento Preencher/Ajustar/Original sem deformar o vídeo;
- talkback IT-Blue/Mibo permanece candidato até validação positiva;
- AKDB Core revision 7.

### 0.2.26 — Channel Health Monitor
- monitor periódico de saúde por canal sem manter todos os vídeos decodificados;
- perda de sinal e câmera IP/proxy offline passam a ser estados distintos quando o provider fornece telemetria nativa;
- Hikvision/ISAPI expõe IP, porta e protocolo configurados para canais IP;
- alertas de canal usam confirmação em duas verificações consecutivas e recuperação automática;
- falha do DVR/NVR permanece agregada no equipamento para evitar tempestade de alertas;
- aba Saúde e inventário de Canais passam a mostrar estado operacional e endpoint configurado.

### Próximos focos após 0.2.26
- homologar fisicamente o Channel Health Monitor no MHDX e Hikvision;
- acrescentar telemetria nativa Intelbras/Dahua para IP de câmera e VideoLoss quando validada no hardware real;
- homologação do áudio do Canal 5 do MHDX em campo;
- identificação das duas lentes fixas reais da IT-Blue com deduplicação temporal/visual conservadora;
- diagnóstico e implementação de talkback por provider;
- AKDB Homologation + Device Intelligence;
- Capacity/Performance Monitor e benchmark progressivo para instalações de até 288 canais.

### 0.2.27 — Update Center + ArtinUpdates
- Centro de Atualizações integrado à Configuração;
- canais Stable/Beta e checagem opcional ao iniciar;
- manifesto `artin-update-manifest-v1` centralizado no ArtinUpdates;
- SHA-256 obrigatório e suporte a assinatura Ed25519;
- download/instalação somente com confirmação explícita;
- helper externo com encerramento coordenado e watchdog de 10 s;
- relançamento e notas pós-update preservados;
- publisher auxiliar para gerar manifestos e checksums.

### 0.2.28 — Focused Close Recovery + Official Updates + Talkback Lab
- restauração segura do mosaico ao fechar a câmera ampliada;
- correção equivalente em janelas independentes;
- preservação dos demais streams e do fullscreen anterior;
- workspace persistido pelos tiles reais durante foco;
- URL oficial ArtinUpdates pré-configurada;
- IT-Blue X3-WE2Q com talkback DVRIP/G.711A experimental para validação física;
- Mibo iMX C: vídeo/áudio de escuta validados; perfil específico AKDB e Intelbras-1 registrado como candidato. Talkback local continua pendente até homologação por modelo/firmware.

### Próximos focos após 0.2.28
- publicar/provisionar a URL oficial do ArtinUpdates e a chave pública Ed25519;
- integrar o mesmo contrato de manifesto nos demais aplicativos Artin sem duplicar lógica;
- homologar fisicamente o Channel Health Monitor no MHDX e Hikvision;
- telemetria nativa Intelbras/Dahua para VideoLoss e endpoint de câmera IP quando validada;
- talkback por provider e duas lentes fixas reais da IT-Blue;
- AKDB Homologation + Device Intelligence;
- Capacity/Performance Monitor e benchmark progressivo para instalações de até 288 canais.
