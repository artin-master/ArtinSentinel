# Intelbras postAudio Diagnostics — 0.2.38

A HTTP API V3.81 mantém dois formatos documentados para `POST /cgi-bin/audio.cgi?action=postAudio`: `singlepart`, como fluxo contínuo, e `multipart/x-mixed-replace`. O exemplo multipart usa partes `Audio/G.711A` com `Content-Length: 800`.

A partir da especificação V3.61 existe também `POST /cgi-bin/api/devAudioDecode/empty`. Para talkback, `sourceType=0`; a resposta `flag=true` indica buffer vazio e `flag=false` indica que há dados no buffer. A API pode não existir em firmwares cuja versão HTTP seja anterior.

Na 0.2.38 o Sentinel:

- inicia com singlepart;
- em fechamento precoce pelo peer, tenta multipart no mesmo acionamento do MIC;
- consulta o buffer de forma assíncrona para não interromper o envio do áudio;
- não trata a simples saída de dados do PC como confirmação do alto-falante remoto;
- registra resposta HTTP observável, estabilidade, frames e KiB transmitidos.

O NetSDK continua reservado como fallback futuro caso o firmware exponha `audio OUT` mas rejeite ambos os formatos HTTP documentados.
