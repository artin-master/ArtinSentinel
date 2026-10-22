# Hybrid Channels + Direct IP Cameras — 0.2.6

## Objetivo

Separar definitivamente dois fluxos:

- gravador: enumeração de canais lógicos, inclusive canais IP adicionais;
- câmera IP direta: um dispositivo de câmera não é tratado como DVR/NVR e recebe um onboarding de stream próprio.

## Câmera IP direta

O Sentinel tenta, em ordem:

1. ONVIF Device Service;
2. Media/GetProfiles;
3. Media/GetStreamUri;
4. validação RTSP dos perfis retornados;
5. fallback por padrões AKDB/provider conhecidos;
6. somente após validação, grava Main/Sub no cadastro lógico do canal 1.

A câmera permanece com um único canal lógico por padrão. Perfis Main/Sub não são contados como câmeras diferentes.

## Gravadores híbridos

A enumeração não usa o número comercial do modelo como limite semântico. Canais 1..N são testados dentro de uma janela limitada de segurança. Para Intelbras/Dahua-family, cada canal pode usar variações de query distintas e Main/Sub são validados independentemente.

## Correlação futura

Quando uma câmera for encontrada diretamente e também por um canal IP de gravador, a base passa a ter informações suficientes para correlacionar as duas rotas sem criar duas identidades visuais. A correlação automática forte continua conservadora e fica para um ciclo posterior.
