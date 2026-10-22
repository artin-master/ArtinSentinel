# Intelbras NetSDK talkback — 0.2.41

## Evidência que motivou o hotfix

Na 0.2.40 a iMX C aceitou login, `CLIENT_StartTalkEx` e pacotes de retorno, mas A/B/C ficaram sem áudio e MODE3 foi recusado. A comparação com o demo Linux oficial `05.Talk` revelou uma diferença concreta: o demo zera `DHDEV_TALKDECODE_INFO` e não preenche `nPacketPeriod`, portanto envia `0`.

## Setup literal A1

1. `DH_TALK_ENCODE_TYPE`: PCM, 8000 Hz, 16 bit, packetPeriod=0.
2. `DH_TALK_SERVER_MODE`.
3. `DH_TALK_SPEAK_PARAM`: mode=0, speaker=0, wait=false.
4. `DH_TALK_TRANSFER_MODE`: transfer=false.
5. `DH_TALK_TALK_CHANNEL`: channel=0.
6. `CLIENT_StartTalkEx`.
7. `localRecordAudio.dav` em frames de 648 bytes a aproximadamente 41 ms.

A2 muda apenas wait=true. A3 muda apenas speaker=1. Cada `CLIENT_SetDeviceMode` é registrado individualmente no diagnóstico.
