# AKDB — Artin Sentinel 0.2.2

A AKDB é a camada de conhecimento de compatibilidade do Sentinel. Ela não é um cofre de senhas e não contém credenciais de clientes.

## Hierarquia prevista

Fabricante → família → modelo → firmware → capacidades/quirks.

Campos e conceitos previstos: `protocol_family`, `compatible_provider`, fingerprints HTTP/ONVIF/RTSP/MAC-OUI, portas típicas, padrões Main/Sub, método de autenticação, categoria de canais, capacidades, origem e estado de validação.

Estados de validação usados no projeto: Documentado, Detectado, Testado e Validado em campo.

## Perfis iniciais

- Intelbras MHDX — família Dahua/Intelbras, RTSP `cam/realmonitor`, validado em campo no MHDX 1004.
- Intelbras MiboCam — câmera direta, ONVIF/RTSP a validar por modelo.
- Hikvision — porta 8000 + RTSP/HTTP e `Streaming/Channels`.
- JFL — provider próprio com compatibilidade Hikvision apenas quando confirmada por modelo/firmware.
- Aitek — câmera IP simples; bloquear enumeração ampla de gravador por padrão.
- IT-Blue — perfil genérico `Web Viewer`/RTSP/34567 continua conservador; a 0.2.11 adiciona um perfil específico X3-WE2Q, condicionado a tokens da própria plataforma para não contaminar outras câmeras IT-Blue.
- IT-Blue GK7202V300 — registrado separadamente como perfil observado somente por cloud, sem inferir acesso local.

## Regra de segurança

APIs/SDKs proprietários só entram quando oficiais, licenciados ou autorizados. Probes da AKDB devem ser somente leitura.
