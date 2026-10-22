# Ciclo funcional 0.2.93 — validação e limites

Este documento distingue os testes automatizados, o relato de validação física
recebido para os equipamentos disponíveis e os testes de hardware que continuam
pendentes. Não amplia a compatibilidade declarada do produto.

## Comportamentos implementados

- PTZ usa capability por perfil/lente e exige rota direta com backend conhecido.
  Um nome genérico como Speed Dome/Ball não seleciona DVRIP automaticamente.
  O helper ONVIF exige um Media Profile com PTZConfiguration; a existência de
  um serviço ONVIF/RTSP, por si só, não habilita PTZ na UI.
- Pressionar/segurar captura equipamento, direção, credenciais e velocidade.
  Soltar, trocar seleção/Site, fechar o canal ou encerrar o mosaico envia Stop
  ao alvo original. A velocidade escolhida vale no próximo movimento.
  Falhas interrompem a renovação; pulsos tentam Stop mesmo após erro no início.
  Resultados atrasados não são registrados na janela de outro equipamento.
- Main/Sub pode ser diagnosticado no inspetor do Live View ou em Equipamentos
  → Canais → Diagnosticar mídia Main/Sub, para qualquer provider com inventário.
  Só são verificadas as rotas salvas. Não há descoberta de caminhos nem gravação
  dos resultados no banco. Cancelar interrompe entre probes; a probe em curso
  termina dentro de seu timeout.
- O relatório mostra codec/resolução de vídeo, presença de áudio, codec/taxa/
  canais de áudio e causas controladas: autenticação, rota ausente, timeout,
  RTSP/rede indisponível, codec local não suportado ou resposta inválida.
  ffprobe identifica faixas; isso não prova decodificação sustentada nem som
  audível. Inventário de decoder desconhecido não é declarado incompatível.
- Saúde conserva debounce, canais e rotas. Alternar SEM SINAL/OFFLINE na mesma
  falha não repete evento. Uma falha apenas transitória não registra episódio;
  a primeira confirmação saudável após falha mostra RECUPERADO, depois OK.
- Talkback usa um registro central das rotas implementadas: DVRIP/Sofia G.711A,
  Intelbras HTTP postAudio/G.711A e Intelbras NetSDK. Todas são experimentais.
  Exige capability, escopo correto e rota direta; a saída do DVR não é tratada
  como retorno para a câmera atrás dele. FFmpeg, microfone, credenciais e NetSDK
  ausentes têm diagnóstico próprio. Uma sessão ativa permanece passível de parada pelo
  botão PARAR após troca de seleção ou perda da capability.
- Diagnósticos de mídia não retornam stderr/URLs externas; as filas de talkback
  removem credenciais conhecidas, headers de autenticação e IDs de sessão.

## Limites mantidos deliberadamente

Não foram alterados schema, descoberta, handshakes proprietários, Publisher,
updater, organização de Equipamentos ou sistema de releases.

O monitor usa checks leves de rotas conhecidas e intervalo mínimo de 120 s por
equipamento. DESCRIBE/SDP positivo não distingue imagem real de tela preta.
Hikvision ISAPI é a fonte nativa existente para perda de sinal/estado de proxy.
Intelbras e outros providers permanecem conservadores em respostas inconclusivas.

A origem autoritativa da última amostra de saúde não é persistida por canal.
A regra legada que substitui certos rótulos por INCONCLUSIVO foi preservada.
Não se ampliou a deduplicação de episódios através desse estado: separar falha
nativa confirmada de falso alerta legado exige uma decisão sobre proveniência.

ONVIF genérico não recebe capability PTZ automaticamente nesta rodada. O helper
foi endurecido, mas novos modelos/perfis exigem evidência específica. DVRIP não
recebeu um timeout proprietário inventado: Stop é solicitado e precisa ser
validado fisicamente, sobretudo na perda de rede/energia da estação.

## Testes automatizados do ciclo

Usar o ambiente e isolamento descritos em TESTING.md. As regressões estão em:

- tests/test_ptz_refinement.py
- tests/test_stream_diagnostics.py
- tests/test_stream_diagnostics_qt.py
- tests/test_channel_health_transitions.py
- tests/test_talkback_readiness.py

Resultado automatizado final conhecido deste ciclo: **594 coletados, 594 aprovados, 0 falhas, 0 erros,
0 skipped**, com 65 regressões novas e todos os 529 testes anteriores preservados.

A execução completa inclui todos os testes existentes, inclusive equipamentos,
instalador, consistência de versão, atualização e serviços Web confirmados.

## Validação física realizada

Segundo o relato de campo fornecido, as funcionalidades principais foram
verificadas nos equipamentos disponíveis; o MHDX 1004 e câmeras IP/MiboCam
disponíveis participaram da validação, sem problemas aparentes nos fluxos
verificados. Este registro não afirma que cada faixa produziu áudio audível,
que a estabilidade contínua de cada stream foi medida ou que o movimento
mecânico de PTZ foi observado. Esses resultados específicos só devem ser
marcados após anotação direta no roteiro de campo.

## Validação física pendente

- **Hikvision:** não havia equipamento disponível neste ciclo; nenhuma validação
  física Hikvision é declarada. Executar o roteiro abaixo na próxima oportunidade.
- Registrar separadamente áudio realmente audível, estabilidade de stream e
  comportamento mecânico de PTZ quando forem observados; testes automatizados ou
  identificação de faixas/codec não substituem essas verificações físicas.

## Roteiro físico por equipamento

Registrar modelo, firmware, conexão direta/via gravador, canal, Main/Sub,
codecs/faixas detectados e resultado observável. Não registrar senhas ou URLs
com credenciais. Usar equipamentos de laboratório para os testes de falha.

### Intelbras MHDX 1004

1. Abrir Canais e diagnosticar Main/Sub de um canal analógico e do canal IP/proxy
   (CAM 5 quando cadastrado). Conferir codecs e faixas com a configuração real.
2. Ouvir a câmera com microfone pelo DVR e comparar Main/Sub; confirmar se a
   faixa identificada produz áudio audível, incluindo vídeo disponível sem áudio.
3. Testar uma credencial incorreta no laboratório: diagnóstico deve indicar
   autenticação, nunca expor senha nem reinterpretar a falha como canal removido.
4. Interromper/restaurar RTSP. Após as verificações de saúde (mínimo 120 s entre
   checks), manter inventário/rotas e evitar eventos repetidos. Sem telemetria
   nativa de sinal, esperar INCONCLUSIVO em vez de presumir SEM SINAL.
5. Verificar que PTZ mediado pelo DVR não envia comando direto e que postAudio
   do DVR não habilita MIC para a Mibo atrás dele. Não homologar retorno ao
   speaker da câmera a partir do simples aceite de áudio pelo DVR.

### Intelbras/MiboCam direta

1. Diagnosticar Main/Sub e verificar codec/faixa/taxa de áudio; testar escuta.
2. iMX C com perfil reconhecido: sem NetSDK, conferir motivo de indisponibilidade.
   Com runtime oficial, testar separadamente A1 referência, A2 espera, A3 speaker
   e B/C microfone ao vivo já existentes. Registrar áudio ouvido na câmera,
   e não somente StartTalk/bytes enviados. Respeitar o limite automático da sessão.
3. Outros Mibo com transport não homologado devem permanecer pendentes; não
   forçar HTTP, DVRIP ou NetSDK por serem da mesma marca.
4. Desconectar microfone/Pulse/ALSA ou remover FFmpeg do ambiente de laboratório:
   conferir a causa exibida e que nenhuma transmissão nova começa.
5. Iniciar sessão suportada, selecionar outra câmera/janela vazia e clicar PARAR:
   a sessão original deve encerrar e liberar o recurso de áudio.

### Câmeras IP diretas

1. Diagnosticar Main/Sub, incluindo uma rota Sub ausente: não inventar caminho.
2. Conferir H.264/H.265, resolução e áudio presente/ausente com a configuração
   real. Decoder listado é capacidade local, não comprovação de reprodução.
3. Em laboratório, exercitar credencial incorreta, serviço RTSP desligado,
   timeout e codec sem decoder local; conferir causas distintas e logs sem senha.
4. Cancelar diagnóstico e trocar seleção/Site: resultado deve permanecer no
   diálogo do equipamento original, sem gravar rotas/capabilities/availability.
5. Câmera fixa ou genérica sem capability não deve oferecer PTZ/MIC por inferência.

### Hikvision

1. Usar diagnóstico de mídia Main/Sub e o diagnóstico de rotas Hikvision já
   existente. Conferir codec/áudio nas rotas salvas e status RTSP nas rotas ISAPI.
2. Desconectar/restaurar entrada analógica e câmera IP/proxy; aguardar duas
   amostras negativas, separadas pelo intervalo de saúde, e uma positiva.
3. Esperar SEM SINAL/OFFLINE, um alerta por episódio e um evento de recuperação;
   na UI, RECUPERADO na primeira positiva e OK na próxima. Nenhum canal é removido.
4. Desligar o gravador: evitar uma tempestade de eventos de perda por canal.
5. PTZ mediado pelo gravador e talkback sem transporte implementado ficam
   indisponíveis; não reutilizar endpoint direto por suposição.

### PTZ/Speed Dome

1. Em modelo/perfil com capability direta, conferir backend exibido e escopo.
   IT-Blue X3 reconhecida usa DVRIP na lente principal; lentes fixas não recebem
   movimento/zoom/MIC. Nome genérico Speed Dome/Ball não basta para habilitar.
2. Testar toque/pulso e pressionar/segurar nas oito direções, com 10%, 45% e 100%.
   Zoom somente quando a capability o declarar; verificar velocidade no próximo
   movimento, sem perder a direção/step do Stop nativo.
3. Soltar e clicar STOP; repetir Stop. Trocar câmera/Site, fechar o canal e sair
   durante movimento: a câmera original deve parar e nenhuma outra deve mover.
4. Interromper a rede durante movimento em local controlado. ONVIF carrega
   Timeout limitado; validar o firmware. DVRIP exige avaliação física da parada
   em perda de comunicação, sem presumir watchdog homologado.
5. Para ONVIF genérico sem perfil operacional conhecido, validar somente leitura
   de GetCapabilities/GetProfiles/PTZConfiguration antes de qualquer ampliação
   de capability. Não habilitar a UI nem testar movimento por inferência de marca.
