# Artin Sentinel 0.2.22 — Hikvision Signal Inventory + Live View Performance

## Hikvision

A leitura de gravadores Hikvision passa a separar três conceitos:

1. equipamento/ISAPI online;
2. canal físico ou IP configurado;
3. stream RTSP realmente com mídia.

`/ISAPI/System/Video/inputs/channels` fornece as entradas físicas e seu estado de sinal. `/ISAPI/ContentMgmt/InputProxy/channels/status` fornece os canais IP/digitais configurados, inclusive quando `/InputProxy/channels` vem vazio em firmware mais antigo. `/ISAPI/Streaming/channels` continua sendo tratado somente como lista de IDs realmente anunciados, sem confundir IDs calculados pelo Sentinel com anúncios do DVR.

No teste de campo do DS-7216HGHI-F1, firmware V4.30.122 build 201107, o equipamento retornou `deviceType=IPC`, apesar de o modelo ser um DVR. A AKDB registra isso como conhecimento negativo: modelo exato prevalece sobre esse campo genérico.

Canais sem sinal/offline são preservados no inventário técnico e no SQLite, mas não aparecem como fontes operacionais no Live View até terem mídia validada.

## Live View

O fullscreen individual deixa de reconstruir a grade. Os mesmos `VideoTile` e `LiveStreamSession` são reposicionados/ocultados, preservando processos FFmpeg, filas de frames, seleção e stream ativo.

Para reduzir pressão de CPU/GUI em mosaicos, a renderização usa escala rápida quando há múltiplos tiles, mantendo SmoothTransformation apenas na visão individual. O FPS alvo também é reduzido progressivamente em grades maiores e o polling principal passa a 100 ms.

O shutdown de `LiveStreamSession` recebe timeout menor; se o FFmpeg não encerra rapidamente após terminate, é finalizado com kill de segurança para não congelar a thread Qt durante trocas de fonte.
