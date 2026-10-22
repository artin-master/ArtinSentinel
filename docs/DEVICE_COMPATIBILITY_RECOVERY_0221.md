# Artin Sentinel 0.2.21 — Device Compatibility Recovery

## Objetivo

Concentrar o ciclo em dois equipamentos confirmados em campo: Hikvision DS-7216HGHI-F1 e IT-Blue X3-WE2Q/XM535D1. Nenhuma escrita remota foi adicionada.

## Hikvision

- `GET /ISAPI/System/deviceInfo` continua validando identidade/credencial.
- `GET /ISAPI/Streaming/channels` passa a fornecer os IDs/canais que o próprio equipamento anuncia.
- O scanner RTSP prioriza esse inventário e usa o limite AKDB apenas como fallback.
- O menu de Equipamentos oferece **Diagnóstico Hikvision (somente leitura)**.
- O relatório separa: autenticação ISAPI, identidade/firmware, IDs anunciados, acesso TCP/554 e Main/Sub.
- Credenciais nunca são gravadas no relatório.

## IT-Blue / XM

- O provider DVRIP consulta apenas objetos de configuração via mensagem 1042 (GET).
- O resultado exposto é sanitizado: nomes dos objetos e contagem de canais sugerida, sem payload bruto.
- Um novo candidato multi-lente é comparado novamente com fontes já aceitas usando capturas quase simultâneas em duas rodadas.
- Se houver coincidência ou evidência insuficiente, o candidato não entra na árvore/Live View.

## Segurança

Todas as novas operações de dispositivo são GET/read-only. Não há alteração de configuração, firmware, rede, usuários, PTZ persistente ou parâmetros de gravação.
