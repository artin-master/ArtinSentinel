# Pós-update — 0.2.7

- O instalador consulta a versão previamente instalada antes de atualizar.
- O marcador de release notes só é criado depois de a instalação terminar com sucesso.
- Se o Sentinel não estiver em execução, ele é relançado após a atualização.
- Na primeira abertura da nova versão, `Novidades desta versão` mostra apenas mudanças da release.
- O estado `last_shown_version` impede repetição da caixa na mesma versão.
- Primeira instalação não força relançamento como se fosse update.
