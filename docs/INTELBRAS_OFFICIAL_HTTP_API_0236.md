# Intelbras Official HTTP API Foundation — 0.2.36

## Fonte

Baseado no documento oficial recebido `HTTP_API_V3_59_Intelbras.pdf` (V3.59, 2024-07-22) e no pacote `General_NetSDK_3.050_PlaySDK_3.042.zip`.

## Probe automático/solicitado

A 0.2.36 usa somente endpoints de leitura:

- `/cgi-bin/IntervideoManager.cgi?action=getVersion&Name=CGI`
- `/cgi-bin/devAudioInput.cgi?action=getCollect`
- `/cgi-bin/devAudioOutput.cgi?action=getCollect`

O resultado é sanitizado e persistido em `metadata_json.intelbras_http_api`. Credenciais continuam exclusivamente no cofre/sessão existente.

## postAudio

A documentação oficial define `POST /cgi-bin/audio.cgi?action=postAudio&httptype=singlepart&channel=1` para fluxo contínuo de áudio, incluindo `Audio/G.711A`. A 0.2.36 **não envia áudio** por esse endpoint. Ela só marca `post_audio_candidate=true` quando o equipamento concreto declara ao menos uma saída de áudio.

## NetSDK

O SDK recebido contém Linux x86-64 e APIs de talk (`CLIENT_StartTalkEx`, `CLIENT_TalkSendData`, `CLIENT_StopTalkEx`) além de enums/funções Cloud/P2P. O Sentinel não redistribui essas bibliotecas nesta versão; a integração NetSDK permanece opcional até validação de licenciamento, carregamento e fluxo Cloud específico Intelbras.

## Segurança

- Sem alteração de configuração.
- Sem `postAudio` automático.
- Sem persistência de senha, nonce, cnonce ou Authorization.
- Probe específico só é executado para identidade Intelbras/Mibo/MHDX.
