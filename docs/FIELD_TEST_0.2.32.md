# Teste de campo — Artin Sentinel 0.2.32

## 1. Inspector / MIC

- Selecionar a Lente PTZ IT-Blue.
- Confirmar `MIC EXP`, C270, ganho e TEST totalmente dentro do painel.
- Arrastar o divisor esquerdo do inspector para alterar a largura.
- Reiniciar o Sentinel e confirmar que a largura foi preservada.
- Confirmar rolagem vertical em janela baixa sem cortar PTZ/Áudio.

## 2. IT-Blue PTZ

- Ouvir áudio.
- Ajustar volume várias vezes sem congelamento.
- Testar C270 em +3 dB e +6 dB.
- Manter talkback como experimental até confirmação física de retorno.

## 3. MHDX 1004 — CAM 5

- Abrir CAM 5 em Substream.
- Ativar áudio.
- Confirmar AAC 16 kHz e backend FFmpeg/Pulse-PipeWire.
- Se ocorrer `503 Service Unavailable`, não clicar novamente: observar retry automático.
- Confirmar que o áudio recupera sozinho ou que o diagnóstico termina com falha clara.

## 4. Diagnóstico

- Com áudio ativo, abrir Diagnóstico.
- O cabeçalho deve mostrar `Estado atual do áudio: ATIVO`, mesmo se houver erros antigos no histórico.
- `Non-monotonic DTS` e `deprecated pixel format` não devem poluir o painel operacional.
- Quando o sink PipeWire aparecer, o histórico deve registrar `controle de volume ativo`.

## 5. Regressão

- Mosaico/fullscreen.
- Janela independente e canais Intelbras.
- PTZ IT-Blue.
- ArtinUpdates.
- Áudio de escuta IT-Blue e CAM 5.
