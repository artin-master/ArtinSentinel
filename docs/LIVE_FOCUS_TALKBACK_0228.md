# Artin Sentinel 0.2.28 — Focus Recovery + Talkback Lab

## Falha corrigida no Live View

Na 0.2.27, o foco individual escondia os demais tiles sem encerrar seus streams. Isso era desejável, mas o fechamento do tile focado limpava o canal sem zerar `_focus_return_state` nem restaurar a geometria. O resultado era um mosaico aparentemente travado em um quadro vazio.

A 0.2.28 introduz uma saída explícita do foco ao fechar o tile. A rotina:

1. encerra somente o stream/áudio/talkback do canal fechado;
2. limpa o estado de foco;
3. restaura visibilidade e geometria dos demais tiles;
4. preserva os demais workers/FFmpeg;
5. preserva fullscreen do mosaico quando ele já estava ativo antes do foco individual;
6. seleciona outro canal aberto ou um quadro disponível;
7. salva o workspace já restaurado.

A mesma regra vale para a janela principal e janelas independentes.

## Persistência

A 0.2.27 possuía um ramo de `save_live_workspace()` que tentava persistir `_focus_return_state["slots"]`, embora esse campo não fosse preenchido ao entrar em foco. A 0.2.28 remove esse ramo: os tiles continuam vivos enquanto estão ocultos, portanto são a fonte correta para salvar o workspace.

## ArtinUpdates

A fonte padrão passa a ser:

`https://raw.githubusercontent.com/artin-master/ArtinUpdates/main`

O resolvedor acrescenta `sentinel/stable.json` ou `sentinel/beta.json`. Configuração local e `ARTIN_UPDATES_BASE_URL` continuam podendo substituir a fonte.

## IT-Blue X3-WE2Q

O transporte já implementado em DVRIP/Sofia usa controle `OPTalk` e áudio G.711 A-law, mono, 8 kHz. Na 0.2.28 ele passa de caminho inacessível para **experimental**, permitindo validação física explícita no equipamento conhecido. A AKDB continua registrando `xm-dvrip-talkback-not-field-validated`, portanto isso não representa homologação.

## MiboCam

Não foi habilitado talkback genérico para MiboCam. O suporte só será anunciado quando existir um transporte local específico validado por modelo/firmware. Essa restrição evita projetar capacidades do aplicativo móvel proprietário para um protocolo LAN não confirmado.
