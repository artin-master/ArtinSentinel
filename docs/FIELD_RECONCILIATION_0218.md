# Field Reconciliation — 0.2.18

## IT-Blue X3-WE2Q / XM535D1

Teste físico da 0.2.17 confirmou Pan/Tilt pelo provider XM/Sofia DVRIP TCP/34567, com cima/baixo corretos e eixo horizontal invertido. A 0.2.18 corrige o mapeamento somente nesse backend.

A câmera possui três lentes físicas conhecidas. A quantidade física não é confundida com a quantidade de streams locais homologados. Apenas visões visualmente distintas e decodificáveis entram no Live View. Canais antigos ficam retidos como evidência, mas não aparecem operacionalmente quando `available=0`.

Zoom permanece não confirmado. Áudio de escuta continua preservado; talkback segue candidato até que o protocolo de retorno seja validado.
