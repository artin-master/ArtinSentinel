# Artin Sentinel 0.2.86 — Configuração portátil

- Configuração → Salvar/Carregar configuração exporta e importa Sites ativos, equipamentos, canais, nomes e layouts.
- Arquivo não leva senhas, tokens, URLs RTSP, MAC ou serial. Novos canais ficam pendentes até salvar credenciais e reler streams.
- Importação preserva cadastros e layouts existentes por Site/IP/canal; repetição não duplica registros.

# Artin Sentinel 0.2.85 — Destaque da câmera

- Duplo clique amplia a câmera dentro da janela atual e o segundo duplo clique restaura a grade sem alterar o estado da janela.
- Evento do rótulo de vídeo não propaga um segundo duplo clique ao tile.
- Selecionar na árvore um canal já aberto localiza seu tile, sem criar outra sessão ou duplicar a imagem.

# Artin Sentinel 0.2.84 — Áudio MIC MiboCam

- Captura NetSDK acumula leituras parciais do FFmpeg até completar cada bloco de 40 ms, evitando perda de amostras no pipe.
- Cadência de envio ao SDK evita rajadas de recuperação após atraso; permanece limitado a 40 ms por bloco.
- Teste físico da MiboCam é necessário para confirmar se o som robotizado foi resolvido.

# Artin Sentinel 0.2.83 — Diagnóstico do MIC e desempenho

- Painel de áudio resume conexão DVRIP, início do talk, captura local e pacotes enviados pelo PC; confirmação acústica permanece teste físico.
- Botão Medições na barra inferior compara as últimas 10 amostras dos mosaicos de 4, 9 e 16 câmeras na sessão.
- Mantém a pausa de janelas ocultas e a identificação específica da lente PTZ.

# Artin Sentinel 0.2.82 — MIC da lente PTZ

- A lente PTZ da IT-Blue X3 usa sua evidência de canal para recuperar a capacidade de MIC experimental quando a identidade geral do equipamento ainda é genérica.
- Lentes fixas não herdam o retorno de áudio da PTZ.
- A disponibilidade real do talkback continua dependente de microfone, transporte local e teste de campo.

# Artin Sentinel 0.2.81 — Desempenho visível

- Barra inferior mostra streams ativos e estimativas de CPU e RAM do Sentinel com FFmpeg.
- Janela independente minimizada ou oculta pausa seus streams e áudio; restauração reabre os canais.
- Conserva o intervalo de saúde de canais de 2 minutos da 0.2.80.

# Artin Sentinel 0.2.80 — Monitoramento mais leve

- A verificação periódica de disponibilidade do equipamento segue a cada 30 segundos.
- A sondagem de saúde de todos os canais agora ocorre no máximo a cada 2 minutos por gravador, sem sobrepor ciclos pendentes.
- Reduz conexões RTSP e carga de CPU/rede em gravadores com muitos canais; a confirmação de falha de canal pode levar mais tempo.

# Artin Sentinel 0.2.70 — Reprodução Hikvision piloto

- Busca de gravações Hikvision via ISAPI ContentMgmt/search, com playbackURI preservado e host redirecionado ao cadastro do Site.
- Mosaico e linha do tempo de até quatro câmeras; a quinta seleção é bloqueada na interface.
- Diagnóstico de Main/Sub por canal, relatório copiável e porta RTSP configurável no gravador.
- A validação no DVR remoto continua pendente; diferenças de fuso do Site devem ser verificadas no teste.

# Artin Sentinel 0.2.69 — Diagnóstico RTSP por canal

- Leitura Hikvision aceita porta RTSP do gravador (padrão 554), salva por equipamento e aplicada às rotas Main/Sub.
- Em Canais, Diagnosticar Main/Sub consulta os dois perfis de cada posição e mostra a resposta sem credenciais; Copiar diagnóstico facilita testes de campo.
- A Reprodução bloqueia a quinta câmera na lista de comparação; mosaico e busca ficam limitados a quatro.
- Resposta RTSP/SDP não é confundida com vídeo efetivamente renderizado.

# Artin Sentinel 0.2.68 — Arquivados e vídeo Hikvision

- Equipamentos arquivados encontrados na rede podem ser restaurados no painel de descoberta.
- Adicionar manualmente o mesmo IP reativa o cadastro arquivado, mantendo inventário e histórico.
- ISAPI Hikvision sem estado de sinal explícito autoriza teste RTSP dos canais; vídeo só aparece após validação.
- Corrigido indicador incoerente de quantidade de canais quando a AKDB conhece menos canais que o inventário.

# Artin Sentinel 0.2.67 — Inventário Hikvision e detalhes

- ISAPI confirma modelo e múltiplas entradas Hikvision antes de tratar o equipamento como câmera IP.
- Ao detectar um gravador, a leitura passa para o scanner de canais sem apagar o inventário anterior.
- Canais já rastreados aparecem com ✓; pendentes são identificados.
- Painel de detalhes possui rolagem própria; integração do atalho desktop com KDE ajustada.

# Artin Sentinel 0.2.66 — Lista de descoberta legível

- A descoberta mostra várias linhas e permite rolar a lista dos resultados.
- As colunas principais usam larguras definidas; a evidência ocupa o restante.
- O painel Equipamentos mantém rolagem da página e divisória ajustável.

# Artin Sentinel 0.2.65 — Áudio, rolagem e PTZ IT-Blue

- Áudio gravado opcional na Reprodução: ouvir, mudo, volume e uma câmera no mosaico.
- MP4 com ou sem áudio, conforme opção na exportação.
- Aba Equipamentos com rolagem vertical em telas menores.
- PTZ da IT-Blue X3 habilitada para a lente identificada pelo exame local mesmo quando cadastrada como Web Viewer.
- Leitura X3 detalha canais DVRIP sem vídeo e as lentes ausentes.

# Artin Sentinel 0.2.64 — Canais e velocidade de reprodução

- Corrige a numeração Intelbras na busca: canal consultado começa em 1; resultado do MHDX começa em 0. Teste de regressão para CAM 2 sem misturar CAM 1.
- Adiciona 0,5×, 1×, 2× e 4× ao player RTSP, reiniciando no horário atual ao trocar de velocidade.
- Modo de comparação de até quatro câmeras, com busca por canal, faixas separadas na mesma linha temporal e mosaico compartilhando o horário selecionado.
- Exportação MP4 continua restrita ao modo de um canal; a comparação por horário não afirma sincronização quadro a quadro.

## 0.2.63 — Reprodução visual e corte

- Filtros e lista compacta à esquerda, player e controles à direita em painel ajustável.
- Faixa do período mostra blocos de gravação e marcações de horário; cursor e clique exibem a hora exata.
- Marcar início/fim limita a exportação MP4 ao intervalo escolhido dentro do trecho selecionado.

## 0.2.62 — Linha do tempo e MP4

- Mantém a lista e o vídeo quando a interface atualiza o mesmo gravador.
- Linha do tempo permite retomar o trecho a partir da posição escolhida; o tempo mostrado é estimado pelo relógio local da reprodução.
- O decoder trata o fim do trecho como conclusão, sem entrar no ciclo de reconexão do Live View.
- Exportação H.264/AAC MP4 em segundo plano com cancelamento e publicação do arquivo somente após conclusão.
- A tela mostra diagnóstico resumido quando a rota RTSP não entrega vídeo.

## 0.2.61 — Reprodução de gravações Intelbras

- Abre por RTSP o trecho encontrado na busca e filtra resultados fora do período/canal solicitado.

## 0.2.60 — Busca de gravações Intelbras

- Reprodução consulta arquivos gravados por canal e período em Intelbras compatível, usando somente os comandos de busca documentados e liberando o finder ao terminar.
- Limita a consulta a 24 horas e 300 registros; mostra início, fim e tipo, sem iniciar download ou alterar a gravação.
- A reprodução do vídeo gravado dentro do Sentinel aguarda validação do resultado no equipamento físico.

## 0.2.59 — Piloto de atualizações privadas

- Serviço local de atualização com chave por cliente, revogação, acesso apenas a manifestos e ZIPs e publicação atômica a partir de um pacote validado.
- Centro de Atualizações guarda a chave privada no cofre do usuário; HTTPS obrigatório e pacote restrito ao mesmo servidor do manifesto.
- Necessita de domínio, HTTPS e conexão de saída da origem até o servidor externo antes de uso remoto; a primeira atualização é manual.

## 0.2.58 — Painéis do Live View e acesso a gravações

- Botão Controles recolhe a lateral direita do Live View, amplia o mosaico e preserva o estado ao reiniciar ou sair da tela cheia.
- Gravadores na árvore de fontes começam recolhidos e mantêm sua preferência de expansão entre atualizações e reinicializações. O filtro pode expandi-los temporariamente.
- Reprodução permite abrir a interface Web de um gravador cadastrado para consultar gravações; busca e timeline nativas aguardam validação das APIs no aparelho.

## 0.2.57 — Equipamentos, logs e instalação

- Site ativo e gestão opcional de Sites agora aparecem dentro de Equipamentos; removida a aba Sites.
- Logs e diagnóstico recolhidos por padrão em Equipamentos mostram canais, RTSP, sessão ao vivo, atualizações e falhas com filtro, cópia, leitura limitada e sanitização de segredos conhecidos.

- O instalador detecta o Sentinel aberto antes de instalar dependências ou substituir o runtime e pede para fechar o aplicativo e verificar novamente.
- Com `--yes` e sem terminal, encerra com erro claro se ainda houver processo aberto; não força encerramento e não altera o aplicativo.
- `--check` continua diagnóstico somente leitura; o atualizador interno segue fechando sua própria instância antes de chamar o instalador e informa que outras instâncias devem ser fechadas.

## 0.2.56 — Diagnóstico de vídeo em NVR Intelbras

- NVRs Intelbras exigem quadro de vídeo decodificado via FFmpeg/TCP antes de marcar uma posição da leitura como disponível. Resposta RTSP/SDP isolada deixa de ser tratada como imagem confirmada.
- Quando falta vídeo, a coluna Evidência indica quadro ausente, autenticação RTSP não aceita, URL inexistente, transporte TCP não aceito ou ausência do FFmpeg, conforme o caso.
- A mensagem de RTSP 401 usa o nome do gravador selecionado, em vez de chamar qualquer NVR de MHDX; se o teste HTTP também retorna 401, essa informação aparece separadamente.
- Abrir todos os canais de um NVR com zero vídeos confirmados agora informa o problema sem preencher o mosaico com posições vazias. Canais pendentes continuam no inventário; a exceção de compatibilidade do MHDX 1004 permanece.

## 0.2.55 — Descoberta e equipamentos no mesmo painel

- Busca local, inclusão, evidências e relatório AKDB reunidos na aba Equipamentos; removida a aba Descoberta duplicada.
- Novo botão Web para o resultado selecionado, habilitado apenas com URL HTTP/HTTPS detectada no mesmo IP e sem credenciais embutidas. O botão Web dos equipamentos cadastrados permanece disponível.
- Atalhos para descoberta levam diretamente à aba Equipamentos.

## 0.2.54 — Inventário de canais via AKDB

- Capacidade da varredura por modelo vem dos perfis AKDB; recuperação de gravadores NVD/1216 presos em cinco posições por gravações antigas, com ajuste manual identificado separadamente.
- Leitura RTSP de 16+ canais recebe tempo proporcional à capacidade. Se o prazo acabar, lista posições ainda não verificadas como pendentes, preservando streams e aliases previamente confirmados.
- Aba Equipamentos reúne dispositivos localizados na rede e cadastrados; permite buscar/adicionar no mesmo fluxo e mostra a contagem de canais listados e com vídeo validado.
- Não presume que posição do modelo AKDB tem stream ativo. Vídeo novo continua dependente de autenticação e RTSP confirmado no equipamento real.

## 0.2.53 — Proteção contra downgrade

- Detecta a versão instalada antes de alterar o sistema; impede que um pacote antigo substitua uma versão mais recente, salvo com `--allow-downgrade` explícito.
- Mostra versão instalada e versão do pacote no diagnóstico `--check`, que continua somente leitura e indica ausência de componentes de vídeo com código de saída diferente de zero.
- Mantém a verificação de FFmpeg, H.264/H.265, RTSP, RGB24 e Qt da 0.2.52.

## 0.2.52 — Pré-requisitos de visualização

- Confere H.264, HEVC/H.265, RTSP e a geração de um quadro RGB24 antes de instalar o aplicativo; `--check` retorna erro quando falta um componente essencial.
- Instala `ffmpeg-free` no Fedora quando faltam os executáveis e `libavcodec-freeworld` quando faltam codecs e o pacote está disponível nos repositórios já configurados. Informa claramente como resolver codecs ausentes quando o repositório não está configurado.
- Testa PySide6/Qt no ambiente Python instalado antes de publicar o atalho; mantém SDKs opcionais e separadas.

## 0.2.51 — Capacidade Intelbras por gravador

- Restringe o limite de cinco posições ao MHDX 1004 identificado; dispositivos Intelbras de modelo desconhecido deixam de herdar esse limite.
- Adiciona perfis candidatos de capacidade 16 para NVD 1416, NVD 1516 e MHDX 1216, com seleção manual persistente de 1–64 posições por gravador.
- AKDB Core r13 diferencia a identidade dos três modelos e atualiza os registros antigos sem conflito causado somente pela revisão global.
- Diferencia posições verificadas de streams com mídia validada na interface e nos eventos.
- Instalador detecta e instala dependências normais, inclui OpenSSH para o conector e falha claramente se os componentes essenciais de vídeo ainda estiverem ausentes. SDK Intelbras passa a ser importada somente pela interface, separadamente.

## 0.2.50 — Conector por Site (piloto)

- Ferramenta `tools/site_tunnel.py` inicia encaminhamentos SSH de saída do Site para um relay e do Sentinel até esse relay; portas limitadas a 127.0.0.1.
- Novo modo de cadastro manual “conector por Site” e leitura de canais Intelbras por portas HTTP/RTSP encaminhadas.
- Diagnóstico do endpoint de loopback calcula presença do DVR pelas URLs encaminhadas, sem confundir o ping local com conectividade externa.
- Guia de implantação e teste físico em `docs/SITE_CONNECTOR_PILOT_0250.md`.

## 0.2.49 — Remote Recorder Pilot

- Cadastro e edição de gravadores em outros locais via endereço alcançável por rede privada/VPN.
- Escolha explícita de protocolo Intelbras/Dahua ou Hikvision/JFL para equipamentos de identidade genérica.
- Diagnóstico orienta sobre conectividade remota; busca sem vídeo confirmado preserva o inventário anterior.
- URLs autenticadas são recusadas no cadastro manual; senhas continuam no diálogo/cofre seguro.
- Integrações por serial cloud/P2P de fabricante aguardam modelo e mecanismo oficial compatível.

## 0.2.48 — X3 Visual Verification

- Decodifica quadro dos canais DVRIP nativos e compara com PTZ/lentes aceitas antes de atribuir a uma lente fixa.
- Canal DVRIP que repete outra imagem ou não fornece quadro comparável deixa de ser anunciado como lente adicional.
- Controles PTZ ocultos ao selecionar lente fixa e atualizados quando muda uma rota de vídeo.

## 0.2.47 — X3 Lens Identity

- Protege a classificação de lentes IT-Blue X3 contra falsos positivos de alias RTSP da PTZ quando a imagem está mudando.
- Confere as rotas nativas das lentes fixas mesmo que a busca RTSP tenha retornado três visões, substituindo o alias provisório no mesmo canal se a rota nativa responder com vídeo.
- Mantém os slots 1=PTZ, 2=fixa 1 e 3=fixa 2 durante buscas parciais; fontes ausentes são marcadas indisponíveis sem renumerar as outras.
- Quando uma rota validada muda, reinicia automaticamente a sessão daquele canal nos mosaicos principal e auxiliares. Se Main/Sub preferido está ausente, usa o outro perfil disponível.
- Falha ou cancelamento de uma nova leitura não invalida as rotas diretas confirmadas anteriormente.
- Teste com a câmera física ainda é necessário para confirmar as três imagens e o movimento PTZ.

# Artin Sentinel 0.2.46 — AKDB Contributions

- Adiciona “Revisar candidatos…” em Configuração → AKDB, com lista, comparação com a identidade oficial instalada e prévia dos dados sanitizados.
- Permite exportar o candidato selecionado como proposta JSON ou enviá-lo individualmente à caixa de entrada GitHub após confirmação.
- Bloqueia envio sem revisão e verifica novamente o conteúdo antes de enviar; mudanças na fila exigem nova revisão.
- Desativa envios automáticos de versões anteriores, inclusive configurações persistidas. O Core oficial só muda por atualização de revisão da AKDB.
- Amplia a sanitização de dados privados em observações (e-mail, IPv6 e pares com segredo).

# Artin Sentinel 0.2.45 — AKDB Change Preview

- Adiciona "Ver alterações" em Configuração → AKDB após conferir o manifesto.
- Mostra quais identidades/extensões serão incluídas ou editadas, com revisões e nomes dos campos alterados.
- Exibe conflitos na prévia mesmo quando o botão de aplicar permanece bloqueado.
- Mudanças no schema de uma extensão na mesma revisão passam a ser reconhecidas como conflitos.
- A prévia é somente leitura e não exibe valores de payload nem altera a AKDB.

# Artin Sentinel 0.2.44 — AKDB Safe Apply

- Aplica o bundle oficial em uma transação SQLite; falha no meio da operação desfaz registros, extensões e metadados da revisão.
- Bloqueia downgrade, reutilização de revisão oficial com conteúdo diferente e conflitos de mesma revisão.
- Mostra o motivo do bloqueio na tela AKDB e mantém o botão de atualização indisponível até a divergência ser analisada.
- Confere que o digest aprovado na revisão corresponde ao manifesto antes de aplicar.
- Preserva a fila de candidatos, evidências e operações de vídeo/áudio da 0.2.43.

# Artin Sentinel 0.2.43 — AKDB Sync + Field Learning

- Adiciona manifesto/revisão oficial independente para a AKDB.
- Adiciona comparação de revisão com resumo de identidades e extensões novas/editadas.
- Atualização da AKDB preserva evidências locais, relatórios de campo e fila de submissão.
- Relatórios candidatos entram automaticamente em uma fila persistente `pending`.
- Adiciona envio opcional para uma caixa de entrada GitHub usando token fine-grained guardado no keyring.
- Reaplica sanitização imediatamente antes do envio (IP, MAC, serial, URL, credenciais e tokens não são enviados).
- Configuração → AKDB ganha controles: Verificar AKDB, Atualizar base, Enviar pendentes e Configurar token GitHub.
- Pode verificar a AKDB automaticamente junto com a checagem de atualização do Sentinel.
- Mantém 0.2.42 Bootstrap Dependencies e 0.2.41 NetSDK Literal Talk sem alterações funcionais.
# Artin Sentinel 0.2.71 — Acesso e destaque

- Criação de senha local na primeira abertura, validação antes de abrir o app e confirmação para fechar a janela.
- Troca de senha em Configuração; verificador PBKDF2 e arquivo de acesso com permissão restrita.
- Duplo clique sobre quadro de gravação alterna entre câmera em destaque e mosaico.
- Saltos de 30 segundos ou 5 minutos na reprodução, sem esperar o avanço em velocidade 4×.
# Artin Sentinel 0.2.72 — Ícones nos controles de reprodução

- Reproduzir, parar, saltar no tempo e baixar MP4 usam ícones com apresentação consistente e dicas de uso.
- Os saltos continuam identificados como 30 s e 5 min para evitar confusão entre direções e duração.
# Artin Sentinel 0.2.73 — Velocidades de reprodução

- Adicionadas as opções 8× e 16× para a reprodução de gravações.
- O áudio acelerado usa etapas de até 2× para compatibilidade com filtros FFmpeg.
# Artin Sentinel 0.2.74 — Zoom digital

- Zoom digital de até 8× com roda do mouse, arraste para mover e botão direito para restaurar em monitoramento e reprodução.
- Senha mínima reduzida para 4 caracteres; senhas já configuradas continuam válidas.
# Artin Sentinel 0.2.75 — Controles do monitoramento

- Barra do mosaico agrupada, com seletor de layout e ações de painel, limpeza, nova janela e tela cheia.
- Ícones padronizados em verde claro e estado ativo visível para o painel lateral.
# Artin Sentinel 0.2.76 — Tesouras e cores nos controles

- Botões de marcar início e fim com desenho de tesoura, rótulo curto e cores distintas.
- Reprodução, parada, saltos e exportação MP4 com ícones de maior contraste e cores por função; verde mais claro e azul harmonizado com o ANL.
# Artin Sentinel 0.2.77 — Paleta geral e ícones coloridos

- Base de toda a interface migrada para azul escuro, com verdes mais claros em seleção e estados positivos.
- Controles de reprodução voltaram a ter fundo neutro; as cores ficam nos desenhos dos ícones.
- Textos secundários e bordas ajustados para manter contraste entre telas.
# Artin Sentinel 0.2.78 — Saúde e AKDB compartilhada

- Falha de rota RTSP sem telemetria nativa é INCONCLUSIVA, sem alarme falso de perda de sinal ou câmera offline.
- Canal de gravador offline não é contado como segunda falha independente.
- Capacidades oficiais mais novas da extensão Sentinel na AKDB compartilhada são lidas em operação para modelos conhecidos; override manual prevalece.
# Artin Sentinel 0.2.79 — Descoberta e AKDB

- Detalhes da busca separam hosts de rede sem evidência CFTV dos candidatos de vídeo e mostram motivos de correspondência AKDB.
- Marca HTTP, porta 8000 e RTSP genérico não promovem automaticamente roteador/AP a câmera.
- Matcher de descoberta lê novos registros Sentinel da AKDB compartilhada, além do catálogo embutido.
