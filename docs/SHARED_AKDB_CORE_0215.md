# AKDB Core compartilhada — 0.2.15

## Objetivo

A AKDB deixa de ser um catálogo exclusivo do Sentinel e passa a ter um núcleo reutilizável por **Artin Sentinel**, **Artin NetLens (ANL)** e **Artin RescNow (ARN)**.

## Regra principal

A identidade de um equipamento existe uma única vez no núcleo. Informações específicas de um aplicativo ficam em extensões de domínio referenciadas pelo mesmo `stable_id`.

### Núcleo comum

- `stable_id` imutável;
- fabricante, família, modelo e variante;
- tipo canônico;
- aliases/identificadores/fingerprints;
- capabilities genéricas;
- protocolos genéricos;
- provenance/origem;
- estado de validação/homologação;
- domínios consumidores;
- revisão do registro.

### Extensão Sentinel

- provider de CFTV;
- família de protocolo;
- streams e codecs de vídeo;
- RTSP/ONVIF;
- áudio e PTZ;
- quantidade/categoria de canais;
- protocolos nativos específicos de VMS.

Extensões futuras podem usar os domínios `netlens` e `rescnow` sem alterar a identidade central.

## Armazenamento compartilhado

Por padrão a base local é:

`~/.local/share/artin/akdb/akdb.sqlite3`

Ela usa SQLite/WAL para permitir leitura concorrente pelos aplicativos. O caminho pode ser sobrescrito em desenvolvimento/testes com `ARTIN_AKDB_PATH`.

A tabela `records` contém o catálogo compartilhado, `domain_extensions` contém detalhes por app e `evidence` guarda observações/testes. Evidência de campo não é conhecimento homologado.

## Proteção de versão

O banco guarda `schema_version`, `core_version` e revisão por registro. Um app com registro de revisão mais antiga não pode sobrescrever uma revisão mais nova já existente. Conteúdo divergente com a mesma revisão é preservado como conflito em vez de substituir silenciosamente a base.

## Evidência e homologação

O Sentinel pode registrar uma exportação técnica sanitizada como `field-test / candidate`. São omitidos nomes de exibição, IP, MAC, serial, credenciais e URLs autenticadas. A promoção para homologado exige revisão posterior e nova revisão da AKDB.

## Intercâmbio

O módulo `artin_akdb.exchange` define `artin-akdb-bundle-v1`, contendo:

- schema/core version;
- registros centrais;
- extensões de domínio.

O mesmo contrato será reutilizado na integração do ANL e ARN.
