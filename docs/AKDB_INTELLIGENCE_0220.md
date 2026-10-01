# Artin Sentinel 0.2.20 — AKDB Intelligence + Persistent Identity

## Objetivo

A 0.2.20 transforma a AKDB de catálogo passivo em participante ativo da descoberta. O Sentinel coleta evidências somente leitura, normaliza o que observou e consulta o AKDB Core antes de aceitar uma classificação genérica.

## Fluxo de identificação

1. Descoberta LAN/HTTP/RTSP/ONVIF coleta evidências.
2. O `artin_akdb.matcher` compara fabricante, modelo reportado, aliases, identificadores, fingerprints e protocolos.
3. Um match de alta confiança pode definir tipo canônico/subtipo e estratégia preferida.
4. O Sentinel preserva override manual quando existir.
5. Equipamento sem match suficiente vira candidato à homologação, não uma identidade inventada.

A decisão é explicável: confiança e motivos do match são persistidos como cache operacional no Sentinel, enquanto a identidade homologada continua pertencendo ao AKDB Core compartilhado.

## Tipo, subtipo e estratégia

O AKDB Core passa a poder responder não apenas `o que é`, mas também `como abordar` o equipamento:

- `canonical_type`
- `subtype`
- `preferred_strategies`
- `avoid_strategies`
- `negative_knowledge`

Exemplo: um DS-7216HGHI-F1 prefere ISAPI/RTSP de gravador Hikvision e evita scanner genérico de câmera. Uma plataforma H2-52PGX é tratada como câmera fixa/bullet e evita enumeração de gravador.

## Plataforma H2-52PGX

A plataforma `H2-52PGX` recebeu identidade genérica própria (`artin.device.oem-h2-52pgx`). Ela não é automaticamente tratada como um modelo comercial Aitek/SIGMA apenas pelo código da plataforma. Se o fabricante for observado separadamente, essa evidência é preservada.

## Identidade persistente e Descoberta

A tela Descoberta agora lista somente dispositivos novos. Um equipamento já cadastrado é reconhecido por evidência de unidade física forte:

- IP/endpoints já associados;
- MAC dentro do mesmo Site;
- serial;
- UUID.

AKDB ID/modelo nunca são usados sozinhos para concluir que duas unidades físicas são o mesmo aparelho.

Equipamentos conhecidos, inclusive arquivados ou offline, não voltam para a lista. Uma mudança de IP ou segundo endpoint atualiza o cadastro existente. Após exclusão permanente, o equipamento poderá ser descoberto novamente.

## Relatório de homologação

A Descoberta oferece `Relatório AKDB`. O arquivo `artin-akdb-field-report-v1` é sanitizado e não inclui:

- credenciais;
- IP;
- MAC;
- serial/UUID;
- imagens;
- áudio.

O relatório registra identidade provável, confiança, evidências, protocolos e contexto Sentinel. Ele entra como `candidate` e nunca promove conhecimento automaticamente.

## Controle de versões/sincronização

AKDB schema 2 adiciona metadados separados:

- `schema_version` — compatibilidade estrutural;
- `core_revision` — revisão oficial do conhecimento comum;
- revisão por domínio (`sentinel`, futuramente `netlens`/`rescnow`);
- `local_generation` — alterações/evidências locais;
- `last_uploaded_generation` — última geração considerada enviada;
- `upload_pending` — indica material local pendente.

Uma atualização oficial não incrementa `local_generation`. Evidências e relatórios locais incrementam.

## Proteção contra sobrescrita

Conhecimento com revisão mais alta não é rebaixado. Conteúdo divergente na mesma revisão gera conflito e preserva o registro existente. A migração 0.2.19 → 0.2.20 eleva as revisões oficiais para evitar conflito artificial causado pela mudança do schema.

## Fonte única

Sentinel mantém somente cache operacional (`akdb_stable_id`, confiança, tipo/subtipo observado). A identidade compartilhada, homologação e estratégia pertencem ao `artin_akdb`, preparado para uso também por Artin NetLens e Artin RescNow.
