# Artin Sentinel 0.2.25 — Audio Stability + Recorder Route Intelligence

## Objetivo

Consolidar os testes físicos da 0.2.24 sem introduzir novas regressões de vídeo: estabilizar o áudio de escuta, isolar o Canal 5 IP/proxy do MHDX 1004, reduzir re-probes desnecessários e melhorar o enquadramento do mosaico.

## Áudio de escuta

O slider não deve mais controlar volume por meio de encerramento/reabertura da sessão RTSP. Quando `pactl` está presente, o Sentinel localiza o sink-input associado ao processo do player e altera o ganho em tempo real. O stream permanece conectado.

Escala operacional:

- 0: silencioso;
- 75: nível original (1,0×);
- 100: até aproximadamente 2,0× (+6 dB).

A status bar mostra o canal ativo, por exemplo `Áudio: MHDX 1004 • CAM 05`. Estados transitórios de conexão/falha utilizam a mesma área para evitar mensagens espalhadas pela interface.

## MHDX 1004 e Canal 5

O provider passa a separar explicitamente duas fases:

1. validar os canais analógicos 1–4;
2. somente depois validar o Canal 5 IP/proxy.

Essa separação evita que timeouts/fallbacks do canal híbrido interfiram nos quatro canais já comprovados. Para o Canal 5, o último stream Main/Sub que efetivamente produziu frame é persistido e priorizado na próxima abertura automática.

O áudio do Canal 5 pode ser verificado via próprio DVR mesmo quando o cadastro anterior ainda o marcou como sem áudio. Se o probe confirmar uma trilha, codec/amostragem/modo são atualizados no banco operacional.

## Talkback

Escuta e talkback são capabilities distintas. Testes físicos mostraram escuta funcional na IT-Blue e MiboCam, porém retorno de áudio ainda não foi validado. A AKDB registra o caminho de talkback como candidato e conhecimento negativo para a implementação experimental anterior; MIC não deve ser anunciado como funcional até uma validação positiva por provider.

## Mosaico

Cada tile suporta três modos de apresentação:

- **Preencher:** mantém proporção, amplia até ocupar o tile e aplica crop central do excedente. É o modo indicado para mosaicos sem tarjas.
- **Ajustar:** preserva todo o frame e pode deixar barras quando a proporção da câmera difere da do tile.
- **Original/1:1:** evita upscale e preserva escala original quando possível.

Nenhum modo modifica resolução, codec, bitrate, Main/Sub ou gravação. É apenas uma transformação de apresentação do frame decodificado.

## Próximos passos de campo

Prioridade: MHDX CAM 1–5, áudio CAM 5 via DVR, slider sem reconexão, status bar, Mibo/IT-Blue/Aitek e enquadramento Preencher. Após estabilização, retomar lentes fixas da IT-Blue e AKDB Homologation + Device Intelligence.
