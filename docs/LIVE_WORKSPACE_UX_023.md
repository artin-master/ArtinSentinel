# Live Workspace UX — 0.2.3

## Objetivo

Aproximar o Live View do fluxo operacional de um VMS tradicional sem esconder os controles técnicos do Sentinel.

## Regras

- Um clique em um canal abre a fonte na janela atualmente selecionada.
- Após a abertura, a seleção avança para o próximo slot vazio.
- Se o operador clicar explicitamente em um tile ocupado e depois clicar em outro canal, somente aquele tile é substituído.
- Botão `×` fecha apenas o canal daquele tile e encerra sua sessão/reconexão.
- Clicar no nome de um DVR/NVR abre seus canais em sequência.
- Ao abrir todos os canais de um dispositivo, canais já abertos desse mesmo dispositivo são fechados antes para evitar duplicidade.
- Fontes de outros dispositivos são preservadas enquanto houver capacidade.
- O workspace continua persistido por Site.

## Geometria

O `QGridLayout` retém stretches mesmo após remover widgets. A 0.2.3 zera stretches/minimums antigos antes de reconstruir a grade, corrigindo o caso observado em campo ao trocar 16 → 4.
