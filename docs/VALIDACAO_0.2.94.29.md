# Validação 0.2.94.29 — 21/10/2026

## Resultados finais

113 testes funcionais selecionados passaram. A rodada inclui fabricantes, cores,
catálogo, cadastro assistido, conflitos de identidade, descoberta, AKDB compartilhada,
permissões, pesquisa Hikvision, calendário/rotas, transferência, régua e instalador.

52 testes de mídia passaram executados por arquivo em processos separados:
- test_persistent_playback_029422.py: 7 passed in 36.83s
- test_shared_playback_02948.py: 4 passed in 8.82s
- test_speed_switch_029426.py: 4 passed in 2.23s
- test_recording_history_02946.py: 11 passed in 5.94s
- test_recording_export_0262.py: 4 passed in 0.56s
- test_export_options_029419.py: 5 passed in 29.29s
- test_query_session_029424.py: 5 passed in 16.23s
- test_playback_acceleration_029421.py: 6 passed in 12.26s
- test_continuous_playback_029425.py: 6 passed in 26.57s

Os conjuntos se sobrepõem em alguns recursos, não foram executados todos os testes
do projeto. Não houve acesso a DVR físico. As rotinas de mídia usam NetSDK C++
sintético (sem sockets), callbacks, pipes e FFmpeg local com mídia gerada. As buscas
Hikvision usam respostas ISAPI substituídas; testes confirmam roteamento e comandos,
não desempenho efetivo nem sincronismo de um gravador real.

## Ocorrência durante a regressão

Na execução agrupada de mídia, o teste
`test_video_sessions_reuse_login_and_shutdown_cleans_it` falhou na expectativa de
zero logouts antes do shutdown. Passou isoladamente na .28 e na .29; o arquivo
completo também passou nas duas versões e na rodada final por arquivo.
O motivo da diferença entre execução agrupada e isolada não foi determinado.
Isso não foi tratado como correção do produto nem ocultado alterando a asserção.
Os arquivos Intelbras `intelbras_cloud.py`, `intelbras_cloud_worker.py`,
`playback_session_pool.py`, `live.py` e `shared_playback_audio.py` são idênticos à .28.
A execução agrupada integral não é declarada aprovada nesta entrega.

## Verificações adicionais

- Persistência de cor e aliases sem promover registros Core/homologação.
- Preferências locais sobrevivem à sincronização oficial e preservam o schema Core.
- Cor somente no intervalo de texto da marca; canais não recebem referência de fabricante.
- Paleta, árvore e catálogo renderizados em Qt offscreen e inspecionados no tema atual.
- Catálogo distingue validação geral de validação específica; firmware ausente não é inventado.
- Referência manual preenche vazios e preserva identificação divergente.
- Descoberta real da UI simulada com MAC diferente no mesmo IP: nenhum cadastro alterado.
- Origem antiga/malformada não quebra o painel de evidências.
- Cancelamento Hikvision antes da consulta não envia requisição; página repetida encerra com parcial.
- Contadores de descartes e avisos preservados na consulta multicanal.
- Comandos de vídeo/áudio recebem URI Hikvision; taxa solicitada não comprova taxa física.
- Compilação Python, sintaxe shell, versão, wheel, manifesto e CRC do ZIP conferidos na montagem.

## Pendências físicas

Prioridade: pesquisa, reprodução 1×, saltos na régua, áudio, 2×/4×/8× e exportação
no Hikvision da unidade. Repetir uma reprodução/exportação Intelbras local e Cloud.
Conferir cores/persistência e cadastro assistido. Roteiro: `TESTES_0.2.94.29.md`.
Este pacote é para validação; não houve publicação externa nem alteração no NetLens.
