# Live View UX + PTZ Hold Control — 0.2.16

A 0.2.16 reduz a densidade do painel operacional do Live View e prioriza vídeo e controle. A toolbar usa ações compactas com tooltip, enquanto Stream, Áudio e PTZ são contextuais à fonte selecionada.

O inspector lateral usa rolagem vertical automática. O conteúdo preserva o tamanho mínimo dos controles; em alturas menores, o operador rola o painel em vez de o Qt comprimir o D-pad, Zoom ou sliders. A barra horizontal permanece desabilitada.

O resumo do Site (quantidade de equipamentos e estado online/offline) foi movido para a barra de status ao lado da versão do aplicativo e recebe um ícone de contexto. A seleção atual passa a ser apresentada em um card compacto com ícone, título, uma linha de contexto e badge de estado. Ações menos frequentes, como renomear o canal e a opção de perguntar o stream na abertura, ficam em um menu compacto `⋮`; o botão duplicado para abrir Configuração foi removido. Stream, Áudio, PTZ e Diagnóstico usam ícones discretos e tooltips para reduzir texto sem perder clareza.

## PTZ

Para fontes com capability PTZ direta/candidata, o D-pad trabalha em modo pressionar-e-segurar. `ContinuousMove` usa timeout curto no equipamento; o Sentinel renova o comando enquanto o botão continua pressionado e envia `Stop` ao soltar. A fila de renovação é limitada para evitar backlog.

A IT-Blue X3-WE2Q / XM535D1 continua como `onvif-candidate`. Se o equipamento de campo não expuser PTZ ONVIF, a falha fica explícita no diagnóstico e o próximo provider a implementar será o transporte OEM/XM/DVRIP 34567, sem alterar o vídeo RTSP já funcional.

## Áudio

A interface de áudio foi compactada, mas o pipeline funcional não foi expandido nesta versão. A reprodução local continua pendente de diagnóstico dedicado após a validação do PTZ.

## AKDB

Nenhuma regressão intencional: a Shared AKDB Foundation 0.2.15, IDs estáveis, banco compartilhado e extensões por domínio permanecem inalterados.
