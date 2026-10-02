# IT-Blue multi-lentes — correção de revalidação no ciclo futuro 0.2.95

Versão interna mantida em **0.2.94**. O trabalho de eventos foi pausado durante
esta correção. Não houve acesso à câmera, alteração de configuração, reboot,
ConfigSet, acionamento de sirene/luz, push ou fechamento de release.

## Causa comprovada e limites da investigação

Uma cópia temporária do banco instalado, incluindo WAL, foi consultada; o banco
original não foi alterado. As três posições e evidências continuavam registradas:

| Posição | Visão histórica | Rota |
| --- | --- | --- |
| 1 | Lente PTZ | RTSP XM `channel=0`, Main `stream=0`, Sub `stream=1` |
| 2 | Lente fixa 1 | `dvrip://IP:34567?channel=1&subtype=0` / `subtype=1` |
| 3 | Lente fixa 2 | `dvrip://IP:34567?channel=2&subtype=0` / `subtype=1` |

O histórico registrava três streams validados em 27/09/2026 e somente um nas
leituras de 02/10/2026. As fixas tinham evidência DVRIP HEVC, 12 FPS, mas
`available=0`; não tinham sido apagadas do SQLite.

A sequência causadora do desaparecimento era:

1. Enumeração nova, sem consultar as rotas conhecidas.
2. Validação RTSP/OPMonitor e comparação visual; timeout, ausência de assinatura,
   comparação inconclusiva ou similaridade parcial omitem a posição do resultado.
3. O resultado direto era tratado como inventário completo. A substituição
   marcava canais ausentes como indisponíveis, mesmo sem prova de inexistência.
4. `_prune_unavailable_live_sources()` fechava/limpava seus tiles.
5. O diálogo após a leitura filtrava `available_only`, mostrando só a PTZ.

Esta lógica já estava no checkpoint anterior ao ciclo 0.2.94. `ip_camera.py`,
`xm_dvrip.py` e a enumeração em `recorder.py` não mudaram entre 0.2.93 e 0.2.94.
Não há registro antigo suficiente para afirmar se o descarte inicial veio de
ffprobe, timeout/sessão DVRIP, decoder ou comparação visual; não foi atribuída
falha física às lentes. Codec/resolução/FPS iguais não provam alias de lente.

## Correção

- A varredura IT-Blue recebe um snapshot dos canais conhecidos e testa primeiro
  suas rotas exatas Main/Sub. Não repete deduplicação visual parcial para revogar
  a identidade de uma lente anteriormente confirmada.
- Uma rota nova ainda precisa da evidência visual existente para evitar inventar
  lentes em uma câmera simples ou promover aliases RTSP da PTZ.
- Resultado parcial/ausência/falha isolada não desativa uma rota direta conhecida.
  Reutiliza o mecanismo de atualização parcial, preservando IDs, nomes/aliases,
  Main/Sub e preferências. Corrige também as linhas legadas desativadas por
  omissão quando ainda contêm a evidência `Rota direta • …` anterior.
- `available` representa elegibilidade de uma rota confirmada historicamente,
  não a saúde atual. Metadata separado `direct_channel_revalidation` distingue
  `validated`, `temporarily_unavailable`, `pending_revalidation` e `retired`.
  Não cria schema, migração, nem altera PRAGMAs.
- Nenhuma quantidade de timeouts gera remoção automática. A API de retirada
  exige evidência explícita `operator_confirmed_visual_alias` e outra posição
  atualmente validada. O scanner não produz essa autorização; não foi criado
  controle de remoção automática ou comando de câmera.
- Os tiles conhecidos são mantidos; a recuperação limitada/backoff da 0.2.94
  continua responsável por cada stream. Somente rotas alteradas e validadas
  reiniciam seu próprio tile, sem reiniciar os demais.
- Canais mostra todo o inventário e separa mídia validada nesta leitura de
  posições anteriormente confirmadas, pendentes de revalidação.
- Diagnóstico por posição registra índice, rota sanitizada, Main/Sub, resultado
  RTSP/ffprobe ou mídia DVRIP, codec/resolução quando informados, erro e decisão
  de identidade; o log registra também a decisão final do inventário. Uma
  comparação parcial semelhante é descrita como inconclusiva, não como prova
  de que uma lente conhecida é alias. Nenhum frame/fingerprint é armazenado.

## Teste físico

1. Usar uma futura build de campo deste checkout; esta correção não foi aplicada
   diretamente à instalação existente nem empacotada nesta rodada.
2. Abrir Configuração → Equipamentos, selecionar IT-Blue → Canais e fazer a leitura.
3. Conferir três posições históricas: PTZ, fixa 1, fixa 2. Se uma não responder,
   deve continuar listada como pendente/temporariamente indisponível, não sumir.
4. Abrir as três visões e conferir cenas distintas. Trocar Main/Sub separadamente;
   verificar alias/nome e preferência preservados.
5. Com as três abertas, repetir a leitura. Não deve aparecer remoção das duas
   fixas nem ocorrer fechamento/reinício indevido dos outros tiles.
6. Se uma fixa falhar, fechar/reabrir apenas ela e repetir a leitura após recuperar
   a rede. A posição e seu ID devem permanecer, com estado retornando a validado.
7. Consultar Logs e diagnóstico → Leitura RTSP: localizar índice nativo 1/2,
   Main/Sub, timeout/erro e decisão final. Guardar o diagnóstico sanitizado para
   distinguir limite de sessões DVRIP, decoder, rede e emissão de mídia.
8. Conferir também uma câmera de uma lente: continua com uma única posição, sem
   fixas fictícias. Não alterar configuração, reiniciar ou acionar luz/sirene.

Pendente: determinar fisicamente por que as probes das fixas foram inconclusivas
na tentativa reportada e verificar revalidação com streams/talkback simultâneos.
Hikvision continua pendente de validação física específica.

## Testes automatizados

Regressões em `tests/test_itblue_revalidation.py`: três lentes, falhas das fixas,
ffprobe falho e recuperação, identidade legada preservada, mídia equivalente com
visões distintas, câmera simples, retirada com evidência explícita, sanitização
e conclusão da leitura sem remover/reiniciar tiles indevidamente.
Resultado: **56 testes focados aprovados**; suíte completa **738 coletados e
738 aprovados**, 0 falhas, 0 erros e 0 skipped, em 79,17 segundos. São nove
regressões novas. `git diff --check` e consistência da versão 0.2.94 passaram.
Não houve teste físico novo nem alteração no banco da instalação existente.
