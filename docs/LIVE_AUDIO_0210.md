# Artin Sentinel 0.2.10 — Live Audio + Media Diagnostics

## Objetivo

Adicionar escuta de áudio ao Live View sem acoplar talkback a protocolos não validados. O áudio continua subordinado à filosofia read-only first: receber áudio é operacional; transmitir microfone só será habilitado depois de o método de backchannel do modelo ser confirmado em campo.

## Modelo de capacidade

Cada canal pode persistir:

- `audio_mode`: `unknown`, `none`, `listen` ou `bidirectional`;
- `audio_codec`;
- `audio_sample_rate`;
- `audio_channels`;
- `audio_detail`.

A AKDB também pode declarar uma capacidade conhecida por modelo/provider. Evidência obtida por ffprobe prevalece para codec/faixa; a AKDB complementa a informação física, por exemplo MiboCam e IT-Blue bidirecionais.

## Live View

- somente uma fonte de áudio por workspace;
- botão de alto-falante aparece apenas em tiles com capacidade de escuta;
- volume fica no painel da janela selecionada;
- troca/fechamento do canal encerra o processo de áudio associado;
- mosaicos densos escondem controles de áudio no tile para preservar espaço;
- janelas independentes de monitoramento possuem sessão de áudio própria.

## Reprodução local

`LiveAudioSession` prefere `ffplay -nodisp` e usa FFmpeg com saída PulseAudio/PipeWire como fallback. URLs autenticadas são materializadas somente em memória e diagnósticos passam pelo sanitizador existente.

## Push-to-Talk

Nesta versão o botão/fundação existe apenas quando a AKDB indica áudio bidirecional. Nenhum áudio do microfone é transmitido. A próxima etapa deve validar por modelo uma destas rotas antes de habilitar o PTT:

1. ONVIF Audio Backchannel;
2. RTSP backchannel padronizado/suportado pelo firmware;
3. provider local específico documentado/validado.

## Modelos de campo nesta fase

- Aitek SIGMA-SEG6050BP / H2-52PGX: escuta, faixa G.711u esperada a partir da interface do equipamento e confirmável pelo ffprobe;
- Intelbras MiboCam: equipamento fisicamente bidirecional; backchannel ainda não validado;
- IT-Blue: equipamento fisicamente bidirecional; backchannel ainda não validado.

## Diagnóstico de codecs

O painel técnico passa a indicar se o FFmpeg local possui decoders H.264, HEVC, AAC, G.711u e G.711a. Se o FFmpeg retornar `no decoder found for`, o worker interrompe a reconexão automática e mantém a causa explícita no diagnóstico.
