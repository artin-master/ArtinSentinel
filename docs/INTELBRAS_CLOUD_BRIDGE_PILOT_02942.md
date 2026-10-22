# Intelbras Cloud via ponte — piloto 0.2.94.2

## Estado

Base: Artin Sentinel 0.2.94.1, commit 8583b5e98f7abb507d4dd4a9930b8a33c4097b2f.
O teste isolado 2.1 exibiu imagem de um MHDX 1204 remoto no Linux em 18/10/2026:
15.045.600 bytes encaminhados integralmente ao player, 2.235 callbacks, login
modo 19, logout e cleanup corretos. O usuário confirmou a imagem.

Esta versão integra o consumidor ao mosaico. A validação automatizada usa SDK
sintético, FFmpeg real e a janela real do AS em modo offscreen. A imagem do DVR
real dentro desta integração ainda precisa ser conferida em campo.

## Requisitos

- Linux x86-64, Python 3.12+, runtime normal do AS, FFmpeg e NetSDK Intelbras
  Linux 3.050 já instalado pelo procedimento existente do aplicativo.
- O diretório do SDK segue o instalador atual e respeita ARTIN_SENTINEL_NETSDK_DIR.
- SIM Next aberto na VM Windows, com Conta Intelbras vinculada e o DVR desejado
  conectado pelo cadastro Cloud (P2P).
- Encaminhamento da VM limitado ao loopback do Linux. A porta interna muda
  conforme o túnel; a porta do Linux pode permanecer fixa.

O piloto não abre um túnel a partir do serial, não substitui autenticação da
Conta Intelbras e não contém chaves Cloud, tokens, DLLs ou bibliotecas do fabricante.
Ele usa a sessão aberta legitimamente pelo operador no SIM.

## Instalar e testar

1. Preserve a VM ligada e o DVR remoto conectado no SIM.
2. Feche o Sentinel e execute o install.sh deste pacote como usuário normal.
3. Abra o AS e escolha o Site desejado.
4. Em Configuração → Equipamentos → Mais, escolha
   “Adicionar Intelbras Cloud (ponte piloto)…”.
5. Informe nome, serial do DVR, porta local da ponte, usuário e senha do DVR.
   No laboratório validado, o Linux usa 55162 e a VM recebe em 28613.
6. Clique Conectar. O SDK executa uma tentativa de login, verifica o serial
   retornado e anuncia a quantidade de canais.
7. Abra o canal 1 no mosaico. Confira a imagem e depois o segundo canal usado.
8. Feche o canal; abra novamente e confira a retomada. Teste depois a janela
   destacada e o fechamento do aplicativo.

O padrão desta etapa é Main stream. O seletor existente usa Main quando não há
Sub cadastrado. Uma posição anunciada pelo SDK não significa câmera conectada
ou vídeo validado; ela será confirmada somente ao receber um quadro decodificado.
O total anunciado pelo SDK pode não incluir todas as posições IP/híbridas.

A senha é enviada ao filho por pipe privado. A opção de salvar usa o mesmo cofre
seguro do AS; sem cofre, a senha fica somente na sessão. Nome de usuário e dados
de conexão podem ficar no SQLite, conforme o padrão existente; a senha não.

## Portas do laboratório

Estado confirmado pelo usuário antes desta build:

| Origem | Destino |
|---|---|
| Linux 127.0.0.1:55162 | VM Windows porta 28613 |
| VM 0.0.0.0:28613 | Túnel do DVR remoto mantido pelo SIM |

Regra VirtualBox: ASCloudTeste,tcp,127.0.0.1,55162,,28613.
Regra de entrada Windows ASCloudTeste55161: nome histórico mantido, porta atual
TCP 28613, programa SIMNext, origem LocalSubnet. Os bloqueios TCP e UDP originais
do SIM foram temporariamente desativados no laboratório. ASCloudTesteSemLAN
existe e está desativada.

Se a porta interna mudar, atualize o destino do encaminhamento e a regra de
entrada. Se mudar a porta do Linux, selecione o cadastro Cloud no AS e use
Editar/Canais/Diagnosticar para atualizar e verificar a ponte novamente.
O serial retornado pelo SDK deve corresponder ao cadastro; um túnel de outro
gravador é rejeitado antes de abrir vídeo.

## Comportamento e limites

- SDK carrega apenas no processo filho com Python -I -S e diretório de bibliotecas
  próprio; Qt e o SDK não compartilham o processo de carga.
- Um processo SDK por sessão de vídeo; uma tentativa por login. Falha de login
  ou identidade interrompe o fluxo, sem tentar outra senha, modo ou perfil.
- Sessões que já entregaram vídeo admitem até duas recuperações com intervalo.
- Fila comprimida limitada em bytes e objetos; excesso interrompe a sessão em
  vez de descartar silenciosamente partes do bitstream.
- O FFmpeg produz os quadros RGB no tamanho normal do mosaico do AS. Não há
  recompressão do vídeo antes da decodificação; a apresentação segue o mosaico.
- O monitor genérico não trata o serial como IP/hostname nem tenta HTTP/RTSP
  para esse cadastro. Sem vídeo recente, o estado automático pode ficar
  desconhecido; isso não é uma nova tentativa de autenticação.
- Áudio, talkback, PTZ, gravação rápida e reprodução remota nesta ponte não são
  declarados validados. Busca de gravações e API HTTP ficam bloqueadas para essa
  rota. Os caminhos locais anteriores permanecem disponíveis.
- O piloto não altera automaticamente VirtualBox, firewall ou configuração do DVR.
- Não há medição de duração prolongada, resolução efetiva, latência ou uso
  específico de relay. O acesso remoto foi observado sob a topologia informada.

## Recuperação

Preserve o instalador anterior e os dados normais do AS. Para deixar de usar o
piloto, arquive o cadastro Cloud criado no teste; isso não remove o DVR local.
Uma reinstalação anterior é downgrade e segue a confirmação do instalador.
O protocolo desta rota não existe na 0.2.94.1.

Ao encerrar o laboratório, restaure os dois bloqueios originais TCP/UDP do SIM,
remova as regras temporárias ASCloudTeste55161 e ASCloudTesteSemLAN e remova
somente o encaminhamento ASCloudTeste. A limpeza não foi executada enquanto a
ponte continua em teste.
