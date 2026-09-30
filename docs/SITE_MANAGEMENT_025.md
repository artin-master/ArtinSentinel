# Site Management — 0.2.5

## Ações disponíveis

- Novo Site
- Renomear
- Arquivar / remover da operação ativa
- Restaurar Site arquivado
- Excluir permanentemente

## Exclusão segura

Um Site que possui equipamentos nunca é apagado de forma silenciosa. O operador deve escolher entre:

1. **Mover equipamentos para outro Site** — preserva equipamentos, canais, histórico por dispositivo e credenciais. O workspace do Site removido é descartado.
2. **Excluir Site e equipamentos** — remove os equipamentos daquele Site, seus canais, vínculos de layout, histórico e credenciais salvas no keyring.

Conflitos de IP no Site de destino bloqueiam a movimentação para evitar fusão acidental de identidades.

## Isolamento

Arquivar ou excluir um Site interrompe os streams vinculados a ele sem encerrar câmeras abertas de outros Sites.
