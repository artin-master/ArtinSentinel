# Teste de campo — Artin Sentinel 0.2.33

## 1. IT-Blue — capabilities por lente

1. Abra `Lente PTZ` e confirme PTZ + `MIC EXP`.
2. Abra `Lente fixa 1` e a terceira visão.
3. Confirme que nessas lentes o painel PTZ não aparece e o MIC não é herdado.
4. Verifique que o vídeo das lentes permanece normal.

## 2. IT-Blue — talkback DVRIP

1. Selecione `Webcam C270 Mono` e ganho +6 dB.
2. Clique uma vez em `MIC`; fale por 5–10 s; clique novamente para parar.
3. No diagnóstico, procurar:
   - `DVRIP 1/5 • login OK`
   - `DVRIP 2/5 • OPTalk Claim aceito`
   - `DVRIP 3/5 • OPTalk Start enviado`
   - `DVRIP 4/5 • áudio do microfone fluindo`
   - `PTT envio • ... frame(s)`
   - `DVRIP 5/5 • OPTalk Stop enviado`
4. Informar se a voz foi reproduzida no alto-falante da câmera.

## 3. Mibo

- Confirmar que vídeo e áudio de escuta permanecem funcionais.
- O retorno ainda não é habilitado; o painel pode indicar `MIC PEND` quando o perfil direto Mibo for selecionado.

## 4. Regressão

- MHDX CAM 1–5 na janela principal e independente.
- Áudio do CAM 5 AAC 16 kHz.
- ArtinUpdates.
- Fullscreen/mosaico e restauração de workspace.
