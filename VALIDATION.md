# Validação 0.2.60

- 359 testes automatizados passaram; compilação Python e verificação de sintaxe do instalador concluídas. PySide6 e gravador físico não estavam disponíveis para validação visual ou consulta real neste ambiente.
- Testes do finder HTTP simulam resposta com gravação e erro; em ambos confirmam a limpeza da sessão de busca. Conferência real com DVR/NVR Intelbras e credencial de reprodução permanece necessária.

## Histórico 0.2.59

- 356 testes automatizados passaram; testes específicos verificam chaves individuais e revogação, proteção da rota do manifesto e do ZIP e bloqueio de chave para URL externa. Compilação Python e sintaxe do instalador passaram.
- O serviço local e o cliente ainda não foram exercitados por HTTPS com domínio e relay reais; publicar em produção requer configurar e testar a infraestrutura externa e instalar esta versão manualmente nos computadores dos clientes.

## Histórico 0.2.58

- 353 testes automatizados passaram; compilação Python, sintaxe do instalador e construção da wheel 0.2.58 concluídas. PySide6 e DVR físico indisponíveis neste ambiente: a aparência final e a navegação Web precisam de teste no computador de instalação.
- Conferir fisicamente: ocultar/mostrar Controles, reiniciar app, expandir/recolher DVRs na árvore e testar filtro; conferir tela cheia e retorno com a lateral recolhida.
- Reprodução abre somente a interface Web registrada do gravador; busca de gravações dentro do Sentinel permanece sem integração validada. Não foi testada com DVR físico neste ambiente.

## Histórico 0.2.57

- Sites foram integrados a Equipamentos e o painel de logs fica recolhido por padrão. A abertura real de vídeo no NVD 1416 depende de teste com o aparelho e credenciais no local.

- O instalador foi testado com processo Sentinel simulado ainda aberto: `--yes` interrompe antes de executar `pip` e pede para fechar o aplicativo; `--check` continua somente leitura.
- A captura física na 0.2.56 do NVD 1416 mantém RTSP 401 e HTTP 401 enquanto o NVD 1516 abriu imagem. Esta versão trata o fechamento na instalação; a autenticação específica do 1416 ainda precisa de verificação com a conta do gravador.

## Histórico da validação 0.2.56

- Testes funcionais confirmam a distinção entre RTSP/SDP que respondeu e quadro efetivamente decodificado nos canais NVR Intelbras, inclusive canal Main válido com Sub indisponível.
- Testes funcionais confirmam que o mosaico de NVR ignora posições sem vídeo e que a exceção do DVR MHDX permanece.
- A suíte completa passou com 348 testes antes do ajuste final da mensagem de autenticação; depois dele, 16 testes dirigidos passaram, inclusive a condição HTTP e RTSP 401. `compileall` e `bash -n install.sh` não registraram erros.
- A captura da 0.2.54 mostra NVD 1416 com RTSP 401 e 0/16 vídeos; outro NVR no mesmo computador alcança 16/16. Validação dos NVD 1416/1516, inclusive a causa específica da autenticação, ainda é necessária em campo. Um teste sintético não reproduz a conta, permissões e o firmware desses gravadores.

## Histórico da validação 0.2.55

- 345 testes passaram (`python3 -m pytest -q`), incluindo URLs Web detectadas do mesmo IP e recusa de credenciais, esquemas não Web e URLs de outro dispositivo.
- Compilação Python e sintaxe do instalador (`bash -n install.sh`) passaram; wheel 0.2.55 construído.
- A aba Descoberta foi retirada do código, com controles, evidências e relatório AKDB reunidos em Equipamentos. A máquina de validação não possui PySide6 nem gravador físico; conferir visualmente os botões e a página Web no computador de operação.
- Hikvision pode informar IP da câmera IP via status ISAPI; o canal Intelbras ainda informa a rota pelo gravador e não extrai o IP da câmera configurada.

## Histórico da validação 0.2.54

- 344 testes passaram; depois do ajuste de texto no cabeçalho, 12 testes dirigidos passaram e `compileall` não registrou erro.
- Teste de prazo esgotado simulou RTSP lento e confirmou que as 16 posições aparecem, com as ainda não testadas indisponíveis.
- Teste de banco confirmou que uma leitura parcial insere canais novos sem retirar a rota ativa de um canal previamente confirmado.
- Capacidade AKDB validada para MHDX 1004 (5), NVD 1416/1516 e MHDX 1216 (16), incluindo registro legado preso em cinco e ajuste manual explícito.
- Tela Qt redesenhada por código; a máquina de teste não tem PySide6 ou DVR físico para validar visualmente a inclusão, autenticação e vídeo real.

## Histórico da validação 0.2.53

- 341 testes automatizados passaram (`python3 -m pytest -q`).
- O teste de regressão simula 0.2.49 instalada e pacote 0.2.41, e verifica que o instalador bloqueia a substituição antes de executar `pip`; também bloqueia pacote 0.2.53 sobre uma 0.2.54 simulada.
- `--check` com uma versão anterior simulada exibe ambas as versões e não executa `pip`.
- Compilação Python, `bash -n` e o pré-teste FFmpeg/RTSP/quadros neste ambiente passaram; wheel 0.2.53 construído.
- O instalador legado 0.2.41, já distribuído, não pode ser alterado retroativamente: para reparar máquinas afetadas, executar este pacote mais recente.

## Histórico da validação 0.2.52

- 338 testes passaram (`python3 -m pytest -q`); wheel 0.2.52 construído; `bash -n` e compilação Python sem erros.
- O pré-teste real neste ambiente detectou os três executáveis, H.264/H.265, demuxer RTSP e produziu 768 bytes RGB24 para 16×16 pixels.
- `./install.sh --check` com a restrição de root retirada somente em cópia temporária: retorna 0 quando tudo está disponível e retorna 1 quando um FFmpeg simulado não oferece os codecs/quadro.
- Ainda é necessária uma instalação em computador Fedora KDE recém-preparado e a abertura de canais de DVRs reais. PySide6 não está instalado no ambiente de teste; o teste de Qt do instalador foi revisado por código, mas não executado aqui.

## Histórico da validação 0.2.51

- 335 testes automatizados passaram (`python3 -m pytest -q`), incluindo capacidade por modelo, seleção manual, 16 posições mesmo sem vídeo e atualização de revisão da AKDB. O último ajuste de prioridade do modelo explícito passou em 18 testes focados.
- Migração real de uma base local criada pelo código 0.2.50 para 0.2.51: 13→16 identidades, zero conflitos de Core/extensões.
- `ssh -G` confirmou três encaminhamentos efetivos para cada função (Site e operador), presos a 127.0.0.1; `--dry-run` valida argumentos sem conectar.
- Wheel 0.2.51 construído; compilação Python e sintaxe de `install.sh` passaram.
- ZIP corrigido após teste de instalação: `install.sh` e `run-sentinel.sh` preservam permissão executável na extração (`0755`), permitindo `./install.sh`.
- Reprodução RTSP real dos NVD 1416/1516 e MHDX 1216, capacidade efetiva com sinais ativos e interface Qt permanecem para teste físico: PySide6 e os gravadores não estão neste ambiente. O conector SSH remoto herdado da 0.2.50 também depende de relay real para homologação.
