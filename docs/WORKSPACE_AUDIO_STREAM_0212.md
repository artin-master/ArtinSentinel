# Artin Sentinel 0.2.12 — Workspace, áudio e indicador de stream

## Live Audio 2.0

A 0.2.12 deixa de considerar `Popen()` como prova de áudio funcional. O worker executa um preflight com `ffprobe`, procura uma faixa de áudio e só então inicia a saída local.

A ordem de tentativa é:

1. URL do stream atualmente usado pelo tile;
2. outro perfil Main/Sub;
3. URL RTSP legada do canal, se for diferente.

Esse desenho atende câmeras em que o mosaico usa Substream, mas o áudio está presente somente no Main. O diagnóstico diferencia ausência de faixa, ausência de decoder e falha do player/saída local.

O Push-to-Talk continua bloqueado enquanto o backchannel do modelo não estiver validado em campo.

## Reordenação do mosaico

Um tile com câmera pode ser arrastado para qualquer posição da grade. Se o destino estiver vazio, a fonte é movida; se estiver ocupado, as duas posições são trocadas. As sessões de vídeo são remapeadas entre os índices e não são reiniciadas apenas por causa da reorganização.

A nova ordem é salva no workspace persistente.

## Indicador de stream

O tile mostra `● SUB` ou `● MAIN`. O menu de contexto Stream destaca com `●` o perfil efetivamente usado e o painel lateral mostra o mesmo estado. Isso é independente da preferência salva: em modo Automático, o indicador revela o resultado real após fallback.

## IT-Blue X3-WE2Q / três visões

O provider local testa três índices de lente em um conjunto limitado de padrões RTSP conhecidos. Uma URL só vira canal se o vídeo for validado. Para lentes adicionais, um hash de frame é usado para impedir que aliases diferentes da mesma imagem virem canais duplicados.

Se apenas a lente principal for exposta via RTSP, o Sentinel mantém somente esse canal e registra que as demais dependem de investigação do transporte XM/DVRIP/34567; nenhum canal é inventado.
