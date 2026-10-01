# Teste de campo — Artin Sentinel 0.2.31

## Objetivo prioritário
Validar o hotfix de reconciliação do perfil IT-Blue X3 em inventário legado.

1. Abrir o Sentinel após atualizar da 0.2.30.
2. Selecionar **Lente PTZ / Canal 01** da câmera mostrada como `SpeedDome Ball It-blue`.
3. Confirmar que o painel Áudio exibe **MIC EXP**, a entrada de microfone, ganho e **TEST**.
4. Selecionar **Webcam C270 Mono** e executar **TEST** em +3 dB; usar +6 dB se necessário.
5. Pressionar/segurar MIC e validar se o alto-falante da câmera reproduz a voz.
6. Confirmar que câmeras IT-Blue genéricas sem identidade SpeedDome/Ball/X3 não ganham MIC indevidamente.

## Regressões rápidas
- PTZ continua operacional.
- Áudio de escuta continua operacional.
- Mosaico/fullscreen permanece estável.
- Intelbras continua com canais na árvore e em janela independente.
