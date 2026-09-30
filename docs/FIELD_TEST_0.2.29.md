# Plano de campo 0.2.29

## Intelbras MHDX
- Sem nova leitura, conferir árvore lateral: canais 1–5 devem permanecer listados.
- Abrir todos na janela principal e em uma janela independente.
- Canal 5: testar **Ouvir** mesmo se o status anterior estiver inconclusivo; permitir rechecagem pela rota salva do DVR.

## Áudio local / Logitech C270
Source validado no Fedora/PipeWire:
`alsa_input.usb-046d_C270_HD_WEBCAM_200901010001-02.mono-fallback`

- Selecionar a C270 no combo de microfone.
- Testar ganhos 0, +3 e +6 dB.
- Alternar rapidamente Ouvir → MIC → Ouvir e trocar de tile, observando responsividade.
- Reiniciar o Sentinel e confirmar que source e ganho permanecem selecionados.

## IT-Blue X3-WE2Q / XM535D1
### Talkback
- Manter a visão PTZ aberta.
- Pressionar e segurar MIC; falar por 2–5 s; soltar.
- Confirmar se há voz na câmera e se o vídeo/escuta continuam utilizáveis depois.
- Se falhar, exportar diagnóstico; não promover o transporte na AKDB.

### Multilentes
- Executar nova leitura de canais/streams para permitir a tentativa OPMonitor DVRIP.
- Conferir se aparecem somente lentes que efetivamente entregaram keyframe H.264/H.265.
- Comparar visualmente PTZ vs lentes fixas para garantir que não são aliases da mesma visão.
