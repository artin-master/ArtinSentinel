# Artin Sentinel 0.2.13 — Capability Mapping + VMS Devices

## Objetivo

A 0.2.13 deixa de tratar fabricante/provider como sinônimo de capacidade. O Sentinel passa a consultar um mapa conservador por perfil AKDB e separa:

- capacidade confirmada/documentada;
- capacidade candidata que ainda exige validação de campo;
- função mediada por gravador, que não deve ser enviada como comando ONVIF direto;
- função explicitamente não suportada;
- capacidade desconhecida.

## Equipamentos

A aba **Configuração → Equipamentos** mantém a tabela e todas as ações existentes, mas passa a usar um workspace próximo de VMS: inventário filtrável do Site à esquerda e detalhes contextuais à direita. O painel apresenta identidade, IP, estado, confiança, streams/codecs, ONVIF, áudio, PTZ, limite de canais, recursos e protocolos locais conhecidos.

## PTZ

O painel Live View mantém os 8 sentidos, Stop, Zoom e velocidade, com ergonomia revisada. O controle só é habilitado como PTZ direto quando o perfil indica ONVIF direto/candidato. PTZ mediado por gravador, como Coaxitron em DVRs, é informado mas não recebe comandos ONVIF incorretos.

## Hikvision DS-7216HGHI-F1

Perfil AKDB dedicado:

- 16 canais analógicos;
- até 2 canais IP adicionais;
- dual stream;
- RTSP Hikvision `/Streaming/Channels/{canal}01` e `02`;
- service 8000 e ISAPI registrados como candidatos de integração local read-only;
- enumeração RTSP limitada a 18 canais quando o perfil está confirmado.

## Intelbras VIPC 1230 D G2

Perfil AKDB dedicado:

- câmera fixa 2 MP;
- 2 streams;
- Main `/cam/realmonitor?channel=1&subtype=0`;
- Sub `/cam/realmonitor?channel=1&subtype=1`;
- ONVIF Profile S/T;
- H.264/H.265/MJPEG;
- PTZ e áudio marcados como **não suportados** para este perfil, evitando botões indevidos;
- CGI local mantido como candidato read-only, sem alteração automática do equipamento.

## Segurança operacional

Os planos de protocolo nativo desta versão são descritivos/read-only. Nenhuma ação de configuração remota é executada automaticamente. Credenciais continuam fora da AKDB e não são persistidas em texto puro no SQLite.
