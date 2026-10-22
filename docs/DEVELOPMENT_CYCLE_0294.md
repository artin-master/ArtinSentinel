# Artin Sentinel 0.2.94 — Live View Resilience & Audio Controls

Registro final do ciclo funcional 0.2.94. A versão interna deste checkout é
0.2.94. O ciclo não declara protocolos novos nem homologação além das
observações físicas descritas abaixo. A investigação de eventos, detecção, luz
e sirene da IT-Blue não faz parte desta release e permanece para um ciclo futuro.

## Alterações implementadas

- Fechar/remover uma câmera ampliada restaura o mosaico. Recriar a grade exclui
  também os tiles antes ocultos; a janela destacada restaura sua barra e foco.
- Cada abertura possui seu worker. Stop cancela retries, bloqueia frames tardios
  e impede que um processo criado depois do cancelamento seja adotado. A sessão
  fechada não limpa o cancelamento para voltar sozinha.
- Estados de vídeo distinguem conexão, reprodução, reconexão, autenticação e
  indisponibilidade. O backoff existente foi preservado e ampliado até 30 s nas
  falhas consecutivas sem vídeo. Rejeição explícita de autenticação interrompe
  o ciclo de tentativas. São conservados o perfil e as rotas Main/Sub.
- Em POSIX/Linux, a leitura do pipe tem um limite de 15 s para receber um frame,
  mesmo se o FFmpeg não oferecer timeout de entrada. Um pipe aberto sem frames
  não mantém o tile preso indefinidamente. Outras plataformas conservam o
  caminho anterior de leitura/timeout do decoder.
- A escuta continua única por janela e independente do decoder de vídeo.
  Trocar Main/Sub conserva a preferência de escuta. A passagem para outro player
  aguarda a limpeza do anterior em background, inclusive ao desligar/religar;
  fechar durante essa espera não inicia o novo player. Após uma perda do player
  que já reproduziu áudio, a recuperação usa backoff 2/5/10/30 s; cinco segundos
  de reprodução sustentada reiniciam esse backoff. Stop cancela a recuperação.
- Faixa ausente, mídia não confirmada, decoder ausente e autenticação têm estados
  distintos. Atualizações de volume respeitam cancelamento. Diagnósticos removem
  credenciais conhecidas, inclusive representações codificadas.
- Talkback mantém DVRIP/Sofia, Intelbras HTTP postAudio e Intelbras NetSDK,
  sem ampliar capabilities ou criar protocolos. Cancelamento durante abertura,
  login ou captura não inicia transmissão posteriormente. Stop permanece no
  worker responsável pelo alvo original; o botão PARAR continua disponível.
- Mover o canal acompanha a propriedade da sessão e do diagnóstico de talkback.
  Fechar/pausar o canal encerra seus recursos e não agenda retomada de escuta.
  Retomadas já agendadas conferem identidade, geração, seleção de áudio e Close.
- Encerramento cancela timers e novas aberturas, mantém referências às sessões
  até a limpeza e aguarda os workers num prazo compartilhado. Processos filhos
  são terminados, mortos se necessário, aguardados e têm os pipes fechados.
- Volume de escuta usa curva perceptual; 0% permanece mudo e 100% mantém o
  máximo normal. O ganho MIC é independente, ajustável entre 50% e 200%, com
  100% sem alteração do nível original, limitador antes da codificação, valor
  visível, reset para 100% e botão “Testar”.
- O controle de zoom duplicado foi removido do inspector; zoom no quadrante e
  capability do backend permanecem. Linhas Áudio/Microfone, seleção de
  dispositivo e modo NetSDK/PTT se adaptam a larguras menores; o hotfix MiboCam
  mantém os controles contidos no painel.
- A interface registra estado/diagnóstico sanitizado por canal. Logs e estados
  não incluem credenciais nem conteúdo de áudio/vídeo.

Durante o ciclo funcional não foram alterados schema, Publisher, updater,
capabilities por inferência ou a organização da tela Equipamentos. A versão só
foi avançada nesta preparação oficial da release. Falhas locais no Live View
não criam novos alertas persistidos nem removem canais; o histórico existente
de saúde permanece sob responsabilidade do monitor.

## Validação automatizada

Regressões novas em:

- `tests/test_live_lifecycle_qt.py`
- `tests/test_live_session_lifecycle.py`
- `tests/test_live_audio_lifecycle.py`
- `tests/test_talkback_lifecycle.py`
- `tests/test_media_shutdown.py`
- `tests/test_live_audio_controls_qt.py`

Cobrem callbacks tardios, troca de canal/grade, maximizar/restaurar/fechar,
fechamento durante conexão/retry/captura, Stop repetido, cancelamento de volume,
backoff, encerramento da aplicação e processos filhos reais sem equipamento.
Incluem curva/ganho independentes, controles de percentual/reset/mudo e contenção
do inspector em larguras reduzidas. Resultado final da preparação da release:
**682 coletados, 682 aprovados, 0 falhas, 0 erros e 0 skipped**. A suíte foi
executada com Qt offscreen, dados isolados em `/tmp` e permissão para os
servidores HTTP/TLS loopback dos testes existentes.

## Limites que exigem teste físico

As builds de campo do ciclo foram instaladas nos equipamentos disponíveis. Os
controles Áudio/Microfone foram verificados visualmente; IT-Blue foi usada para
testes de vídeo, áudio/talkback e estabilidade; MiboCam foi usada para validar o
layout e os controles específicos de NetSDK/talkback. Esses testes não homologam
protocolos experimentais: o talkback IT-Blue permanece experimental e modos B/C
da MiboCam não são declarados homologados. A investigação local de eventos,
detecção, luz e sirene IT-Blue ficou fora do ciclo.

Identificação de codec/faixa e limpeza dos objetos não provam áudio audível em
todo cenário nem parada mecânica. Uma chamada bloqueada dentro do NetSDK não
pode ser abortada à força com segurança; retorno e Stop/logout reais dependem do
runtime e firmware. A espera de shutdown usa orçamento compartilhado de quatro
segundos, além da limpeza dos processos filhos, e não declara que qualquer
chamada nativa retorna nesse prazo. Não se inventou watchdog/timeout proprietário
de DVRIP.

**Hikvision permanece pendente de validação física específica por falta de
equipamento** nesta rodada. Não se declara homologação Hikvision com base na
suíte automatizada.

## Roteiro curto de campo

Registrar modelo/firmware, conexão direta ou via gravador, canal, perfil,
codec/faixas e resultado observado; nunca anotar senha ou URL com credenciais.

1. **MHDX 1004:** abrir canais disponíveis, alternar Main/Sub, ampliar/restaurar,
   fechar a câmera ampliada e reutilizar o slot. Interromper/restaurar a rede em
   laboratório: observar backoff, recuperação e preservação de rotas/canais.
2. **MiboCam/IP direta:** repetir em mosaico e janela destacada; fechar durante
   conexão/reconexão, trocar Site/workspace e confirmar que o tile fechado não
   retorna sozinho. Fazer um período de uso contínuo e registrar a duração.
3. **Escuta:** ouvir uma faixa realmente audível; alternar canais e Main/Sub,
   ampliar/restaurar, fechar tile/janela e perder/restaurar RTSP. Confirmar uma
   fonte por janela, ausência de som após Close e recuperação sem players extras.
   Conferir mensagens de faixa ausente e decoder indisponível em laboratório.
4. **Push-to-Talk:** somente em rota direta com capability/runtime disponíveis,
   iniciar, verificar som no destino, trocar seleção e usar PARAR. Repetir ao
   mover/fechar tile, fechar janela, interromper rede e sair do aplicativo.
   Anotar transport usado e resposta real; câmera atrás do DVR não herda talkback.
5. **Recursos:** após fechar o Sentinel, conferir seus processos FFmpeg/ffplay,
   captura local e sockets; os de outros programas não fazem parte desse teste.
6. **PTZ disponível:** movimentar em local seguro, fechar ou mover o canal e
   trocar Site durante o movimento. Verificar parada do alvo original, sem
   comando para o novo alvo. Validar perda de rede apenas sob supervisão; envio
   de Stop não comprova parada mecânica ou watchdog no equipamento.
7. **Hikvision:** executar os mesmos casos e os diagnósticos nativos existentes
   quando houver equipamento. Até lá, manter esta pendência explícita.
