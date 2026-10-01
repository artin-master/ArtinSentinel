# Plano de campo 0.2.30

## 1. IT-Blue X3-WE2Q — exposição do MIC
- Abrir a **Lente PTZ / Canal 01**.
- Confirmar no painel Áudio: badge **MIC EXP**, combo `MIC:` e ganho.
- Confirmar que lentes fixas não recebem MIC automaticamente.
- A escuta deve continuar funcionando como antes.

## 2. Logitech C270 — TEST local
Source conhecido no Fedora/PipeWire:
`alsa_input.usb-046d_C270_HD_WEBCAM_200901010001-02.mono-fallback`

- Selecionar `Webcam C270 Mono`.
- Começar em +3 dB; usar **TEST** falando normalmente.
- Conferir nível médio e pico no painel sem travamento da GUI.
- Se necessário repetir em +6 dB.
- Reiniciar o Sentinel e confirmar persistência do source e ganho.

## 3. Push-to-Talk IT-Blue
- Com a PTZ aberta, manter **MIC** pressionado por 2–5 s e falar.
- Soltar e verificar se a escuta/vídeo permanecem operacionais.
- Como o transporte continua experimental, falha de retorno não deve bloquear vídeo nem áudio de escuta.
- Registrar o diagnóstico técnico caso a câmera ainda não reproduza a voz.

## 4. Regressões rápidas
- MHDX: canais 1–5 continuam na árvore.
- Nova janela: MHDX abre normalmente.
- Alternar Ouvir → MIC → Ouvir sem pequeno congelamento.
- Ampliar e fechar câmera: mosaico continua restaurando.
- ArtinUpdates continua reconhecendo novas versões.
