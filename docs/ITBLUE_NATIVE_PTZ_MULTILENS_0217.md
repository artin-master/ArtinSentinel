# IT-Blue Native PTZ + Multi-Lens — 0.2.17

A 0.2.17 mantém ONVIF como evidência, porém adiciona um provider local candidato XM/Sofia DVRIP para a família X3-WE2Q/XM535D1 em TCP/34567. O controle é estritamente acionado pelo operador e não altera configuração persistente do equipamento.

A descoberta multi-lente deixa de confiar em URL/índice como identidade de lente. O scanner valida vídeo, calcula assinatura visual perceptual e só persiste até três visões distintas. Aliases que repetem a lente PTZ são descartados.

O áudio bidirecional não é implementado neste ciclo; o áudio de escuta permanece inalterado.
