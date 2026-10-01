# Intelbras NetSDK talkback — 0.2.40

## Evidência de campo anterior

Na 0.2.39 a iMX C aceitou login NetSDK em TCP/37777, anunciou PCM/G.711A/G.711u/AAC, aceitou `CLIENT_StartTalkEx`, recebeu dezenas de pacotes de `CLIENT_TalkSendData` e devolveu pacotes no callback. Mesmo assim, não houve som no alto-falante.

## Matriz 0.2.40

- **A / reference-server:** replica o Linux `05.Talk`, enviando o arquivo oficial `localRecordAudio.dav` em quadros de 648 bytes a ~41 ms.
- **B / live-pcm-server:** C270 → PCM s16le 8 kHz → frame privado PCM → `CLIENT_TalkSendData`.
- **C / live-g711a-server:** C270 → G.711A 8 kHz → frame privado G.711A → `CLIENT_TalkSendData`.
- **D / live-pcm-v3:** consulta `CLIENT_GetDevProtocolType` e testa `DH_TALK_CLIENT_MODE` + `DH_TALK_MODE3` com PCM.

O objetivo é separar falha de framing/codec de uma exigência de protocolo V3 sem mudar autenticação, credenciais, seleção da C270 ou rotas de vídeo.

## Provisionamento

O ZIP público não contém NetSDK. O operador seleciona o ZIP oficial uma vez pela interface. O runtime Linux e o áudio de referência ficam em `~/.local/share/artin-sentinel/vendor/intelbras-netsdk` e sobrevivem aos updates.
