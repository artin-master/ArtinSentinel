# Teste de campo — Artin Sentinel 0.2.37

1. MHDX 1004: abrir um canal, selecionar C270, ganho +6 dB, iniciar MIC por 5–10 s e encerrar. Registrar diagnóstico HTTP 1/4…4/4 e confirmar onde o áudio foi reproduzido.
2. iMX C direta: repetir o teste e confirmar se a voz sai no alto-falante da câmera.
3. iMX C: confirmar que Configuração mostra perfil/capabilities de iMX C e não MHDX.
4. Equipamento 192.168.15.3: se ficar inacessível, confirmar que o Live View não executa 12 tentativas Main/Sub/TCP/UDP; deve entrar em host temporariamente inacessível e usar backoff.
5. Regressão: MHDX CAM 1–5, CAM 5 áudio, IT-Blue multilentes/PTZ e PTT DVRIP permanecem funcionando.
