# Intelbras postAudio + Network Backoff — 0.2.37

## Evidência de campo usada

- MHDX 1004: HTTP API v2.0.0, áudio IN 1, áudio OUT 1, postAudio candidato.
- iMX C: HTTP API v2.32, áudio IN 1, áudio OUT 1, postAudio candidato.

## Talkback Intelbras

O transporte só fica disponível quando `metadata_json.intelbras_http_api` confirma:

- API suportada;
- autenticação aceita;
- pelo menos uma saída de áudio;
- `post_audio_candidate=true`.

A primeira homologação usa saída de áudio 1. Esse índice pertence à API de áudio e não é assumido como equivalente ao número do canal de vídeo. Para DVRs, portanto, o teste valida primeiro a saída do equipamento; encaminhamento para uma câmera IP atrás do gravador não é presumido.

## Rede

Erros de socket como `No route to host` são tratados como falha de conectividade. Nessa condição não há benefício em alternar perfil ou transporte RTSP para o mesmo host. O Sentinel abrevia o ciclo, mostra estado de host temporariamente inacessível e usa backoff progressivo.
