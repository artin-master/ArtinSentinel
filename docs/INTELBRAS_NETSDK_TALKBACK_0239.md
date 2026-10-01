# Artin Sentinel 0.2.39 — Intelbras NetSDK Talkback

## Motivação de campo

A iMX C direta anunciou saída de áudio via HTTP API, mas encerrou tanto `postAudio` singlepart quanto multipart em menos de um segundo. O mesmo equipamento falou normalmente pelo aplicativo oficial Intelbras. Pelo MHDX/CAM 5, `postAudio` permaneceu estável e recebeu centenas de frames, porém a voz não foi encaminhada ao alto-falante da Mibo.

Por isso a 0.2.39 trata `postAudio` como saída do dispositivo/diagnóstico quando apropriado e usa o NetSDK oficial como transporte experimental preferencial para talkback direto da iMX C.

## Runtime do SDK

O Sentinel não redistribui os binários proprietários Intelbras. O `install.sh` procura `General_NetSDK_3.050_PlaySDK_3.042.zip` ao lado do instalador, no diretório pai ou em `~/Downloads` e importa somente as bibliotecas Linux x86-64 necessárias para `~/.local/share/artin-sentinel/vendor/intelbras-netsdk/`.

O helper também pode ser executado manualmente:

```bash
python3 tools/install_intelbras_netsdk.py ~/Downloads/General_NetSDK_3.050_PlaySDK_3.042.zip
```

## Sequência de talkback

A implementação segue o demo Linux oficial `05.Talk`:

1. `CLIENT_LoginEx2` na câmera direta.
2. Consulta opcional de formatos `DH_DEVSTATE_TALK_ECTYPE`.
3. Configura PCM 8 kHz / 16 bit.
4. `DH_TALK_SERVER_MODE`.
5. `NET_SPEAK_PARAM` em modo talkback.
6. `NET_TALK_TRANSFER_PARAM.bTransfer = FALSE`.
7. Seleção do canal direto.
8. `CLIENT_StartTalkEx`.
9. Captura C270/PipeWire/ALSA pelo FFmpeg.
10. Pacotes de 648 bytes (`8-byte prefix + 640-byte PCM`) enviados por `CLIENT_TalkSendData` a aproximadamente 40 ms.
11. `CLIENT_StopTalkEx` e logout.

O caminho é experimental até confirmação física do áudio no alto-falante da iMX C.

## UI

Quando o transporte existe no perfil mas o runtime do NetSDK não está pronto, o Live View mostra `MIC INDISP.` e uma explicação textual visível, em vez de apenas um botão discretamente desabilitado. O painel PTZ também recebeu polimento visual sem alterar a lógica por lente.
