# Teste de campo — Artin Sentinel 0.2.35

## 1. IT-Blue Lente PTZ — Push-to-Talk

1. Selecione a Lente PTZ e a Webcam C270.
2. Use ganho +6 dB se necessário.
3. Clique em MIC, fale por 5–10 segundos e clique novamente.
4. Abra o diagnóstico e confirme a progressão:
   - DVRIP 1/6: controle autenticado;
   - DVRIP 2/6: socket de talk anexado à mesma sessão;
   - DVRIP 3/6: Claim aceito;
   - DVRIP 4/6: Start enviado no controle;
   - DVRIP 5/6: áudio do microfone fluindo;
   - DVRIP 6/6: Stop enviado.
5. Registrar se a voz foi audível na câmera e quantos frames foram enviados.

## 2. Lentes fixas IT-Blue

Confirmar regressão: Lente fixa 1/2 continuam sem PTZ e sem MIC e os streams DVRIP continuam abrindo normalmente.

## 3. Intelbras iMX C / Mibo

- Confirmar vídeo e áudio de escuta normalmente.
- O painel deve identificar o retorno como `MIC PEND`, não habilitar transmissão.
- O perfil operacional deve reconciliar `intelbras-mibo` para `intelbras-imx-c` quando o modelo iMX C estiver presente.

## 4. MHDX 1004

Confirmar regressão dos CAM 1–5 e áudio AAC do CAM 5.
