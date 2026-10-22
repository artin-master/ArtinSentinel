# 0.2.94.32 — 22/10/2026

- Inventário extensível Componentes e SDKs: executáveis, codecs, carga nativa isolada e sessões observadas.
- Cadastro orientado pela marca com sugestão de protocolo e preparação opcional do SDK para novos Hikvision.
- Menus agrupados: Adicionar, Editar/credenciais/acesso, Canais, Diagnóstico compatível e Mais.
- Metadados reais de entrada nos tiles e na reprodução; prévia Hikvision Main até 1280×720.
- SDK Hikvision envia comandos de velocidade ao DVR; caminho Hikvision RTSP limitado honestamente a 1×.
- Exportação SDK, erro FFmpeg sanitizado, watchdog/cancelamento, duração/vídeo verificados antes da publicação e confirmação final.
- Destino sem hard link usa criação exclusiva; erros de escrita não passam por sucesso.
- Resultados antigos de reprodução limpos ao alterar backend; avisos repetidos agrupados.
- Cloud Hik-Connect e escuta pelo SDK Hikvision continuam pendentes; validação física da nova aceleração/exportação necessária.

# 0.2.94.31 — 21/10/2026

- Adiciona opção por equipamento “SDK Hikvision local” com porta de serviço e mapa explícito de canais.
- Importa o runtime oficial Linux x86_64 para armazenamento persistente do usuário, fora do instalador.
- Ao Vivo pelo SDK em processo isolado; Auto usa Main, Substream somente por seleção explícita.
- Pesquisa de gravações pelo SDK, integrada à lista, calendário e régua existentes, com limites/cancelamento.
- Reprodução local pelo SDK em 1× como recurso em validação; saltos reabrem o intervalo solicitado.
- RTSP/ISAPI e Intelbras existentes preservados; SDK não é ativado automaticamente.
- Áudio, exportação, velocidades adicionais e Hik-Connect não são anunciados como prontos neste transporte.
- Contenção de processo nativo, fila limitada e pausa/retomada de fluxo gravado para drenar dados.
- Sem nova dependência Python ou pacote do sistema. Dados e instalador Fedora/Mint/Arch preservados.

# 0.2.94.30 — 21/10/2026

- Corrige inventário IP Hikvision compatível quando só InputProxy/channels anuncia
  as entradas: IDs 17/18 não são descartados pelo limite manual de 16.
- Referência de protocolo específica Topway DEFENDER 16-720T3; identidade comercial
  preservada. Nenhuma declaração global de OEM ou homologação de playback.
- EOF não gera watchdog prematuro e pipes só são fechados após terminar o leitor.
- Abrir todos não inicia loops em entradas analógicas explicitamente sem sinal.
- Sem dependências novas. Instalador Fedora/Mint/Arch e dados existentes preservados.

# 0.2.94.29 — 21/10/2026

- Fabricantes e cores com aliases, validação, persistência e histórico local separados do Core.
- Delegate Qt colore apenas a referência de marca; nomes, canais e ícones permanecem independentes.
- Catálogo navegável por fabricante, categoria e modelo com estados individuais de recursos.
- Preenchimento assistido de campos vazios no cadastro e edição, sem inventar acesso ou canais.
- Evidências de descoberta com origem/horário, referência e confiança AKDB e conflitos explícitos.
- Conflitos de identificadores físicos bloqueiam a atualização automática na interface de descoberta.
- Hikvision: cancelamento, MATCHES, páginas repetidas, prazo entre páginas, evidências multicanal e diagnóstico.
- Testes físicos Hikvision pendentes; caminhos de mídia Intelbras preservados.

# 0.2.94.28 — 21/10/2026

- Configurações: ações na mesma barra com quebra automática e estado abaixo.
- Árvore principal e janelas adicionais: marca junto ao equipamento, sem inferir fabricante pelo protocolo.
- Hikvision: uma sessão de busca entre páginas, offset real, até oito páginas, deduplicação e limites de resposta.
- Resposta inválida/falha ISAPI separada de dia vazio; trechos inválidos contam como evidência parcial.
- Calendário/pesquisa usam o protocolo explícito, inclusive equipamentos de marca original diferente.
- DVR autenticado sem inventário utilizável não falha como senha errada; preserva canais anteriores.
- DeviceInfo exige XML de identidade, sem aceitar página HTML como autenticação confirmada.
- Validação física de reprodução Hikvision na Mallet continua pendente.

# 0.2.94.27 — Transferência seletiva de equipamentos

- Seleção de Sites/equipamentos e grupos de dados na exportação administrativa.
- Arquivo v2 sem credenciais, tokens ou rotas de vídeo; leitura compatível com v1.
- Prévia de novos, existentes e conflitos; seleção somente dos novos para importar.
- Comparação conservadora por serial/UUID/MAC, Site/endereço e identificação.
- Não altera cadastros/canais existentes, não restaura arquivados e não sobrescreve layouts.
- Revalidação entre prévia e importação e transação com rollback integral em erro.
- Guia de campo para os próximos testes locais Hikvision/HiLook, sem nova homologação declarada.

# 0.2.94.26 — Reprodução até 8× e perfis de acesso

- Cabeçalho com hierarquia ARTIN/SENTINEL, símbolo maior e altura preservada.
- 16× retirado do seletor; permanecem 0,5×/1×/2×/4×/8×.
- Troca de velocidade separada de Seek: mídia reaberta no cursor atual; autenticação SDK reutilizada quando disponível.
- Controle opcional de administrador/operador com senha administrativa independente; preserva uso anterior até ativação.
- Permissões verificadas em cadastro, edição, reprodução, gravação, exportação, escuta e exportação de áudio.
- Cadastro sem edição não sobrescreve ou restaura equipamentos; callbacks de cadastro Cloud revalidam permissão.
- Elevação administrativa somente nesta execução; salvar configuração retorna ao operador.
- Regressão física de velocidade, áudio, Cloud e permissões permanece pendente.

# 0.2.94.25 — Teste de saltos no mesmo fluxo

- Seek nativo com o mesmo handle de reprodução em um canal sem áudio, dentro da janela original; troca isolada de pipe e decoder, descartando fila antiga.
- ACK com identificador, validação de período/velocidade, um salto por vez; recusa encerra sem repetição automática.
- Áudio, múltiplos canais e rotas sem suporte continuam pelo caminho anterior.
- Descarte de quadros não referenciais no decoder em 8×/16×; desempenho real permanece em validação.
- Mensagens de túnel não anunciam conferência de identidade sem autenticação e eliminam textos consecutivos repetidos.

# 0.2.94.24 — Sessão de consulta de gravações

- Reutiliza autenticação NetSDK entre pesquisas Cloud de dias e canais.
- Separa a conexão de consulta da conexão de reprodução.
- Mantém limites de período/canais, filtros de retorno e erros sem repetição.
- Registra contagens sanitizadas de novos logins/reutilizações no painel técnico.
- Mantém zoom .23, áudio, velocidades e exportações.
- 81 testes locais selecionados passaram; validação física pendente.

# 0.2.94.23 — Zoom da régua

- Roda do mouse amplia/reduz ao redor do horário sob o ponteiro.
- Barra horizontal navega pela faixa ampliada; botão restaura o período completo.
- Marcas 5/15/60 minutos e seleção de horário acompanham a janela visível.
- Zoom local, sem novas consultas ou sessões; preserva reprodução/exportação.
- 64 verificações locais selecionadas aprovadas; validação física do zoom pendente.

# 0.2.94.22 — Reutilização da autenticação na reprodução

- Mantém o login NetSDK ao trocar horário/velocidade e reabrir o mesmo canal.
- Reabre somente o fluxo de mídia para obter novos cabeçalhos de vídeo/áudio.
- Cache em memória: até quatro logins ociosos, expiração em 45 s e limpeza ao sair.
- Recusa reutilização após falhas ou parada nativa não confirmada.
- Preserva consultas, exportações e RTSP; não implementa seek no mesmo fluxo.
- Testes físicos ainda pendentes nesta versão.

# 0.2.94.21 — Reprodução acelerada e pacote limpo

- Libera o seletor Cloud e o comando nativo de velocidade do NetSDK.
- Ajusta timestamps e limita os quadros antes de escalar na reprodução nativa.
- Mede avanço da mídia e usa esse progresso na régua; distingue solicitado/medido.
- Pausa áudio fora de 1×, preservando a preferência de escuta ao retornar.
- Remove relatórios e instruções antigos, caches e builds do instalador.
- Mantém exportação Original/Compacta, áudio opcional e navegação da .20.
- Validação real de velocidade em cada DVR/firmware continua necessária.

# Artin Sentinel 0.2.94.20 — Eventos e Saúde em Configuração

- Barra principal com Ao vivo, Reprodução e Configuração.
- Abas de Configuração: Equipamentos, Eventos, Saúde, AKDB e Atualizações.
- Destinos internos de Eventos/Saúde redirecionados para suas abas; seleção de navegação corrigida para os novos índices.
- Processamento de mídia, exportação e monitoramento preservados.

# Artin Sentinel 0.2.94.19 — Opções Original/Compacto e áudio independente

- Seletor de qualidade MP4 na Reprodução; Original continua padrão no Cloud aprovado.
- Compacto H.264 até 720p/15 FPS, alvo 900 kbit/s e AAC mono 48 kbit/s opcional.
- MP4 sem áudio funciona nos dois perfis, independente de ouvir a gravação.
- Estimativa na janela de salvar e nomes sugeridos identificam compacto/sem áudio.
- Perfis compartilhados pelos exportadores Cloud e RTSP; Original RTSP passa a copiar vídeo.
- Layout, áudio de reprodução e diagnóstico anteriores preservados. Compacto e RTSP local aguardam validação física.

# Artin Sentinel 0.2.94.18 — Exportação com vídeo original e diagnóstico

- MP4 Cloud mantém codec de vídeo original e converte áudio disponível para AAC, evitando recodificação H.265 → H.264 obrigatória.
- Diagnóstico opcional de bytes recebidos/enviados pelo SDK, tamanho de arquivo, quadros, tempo de mídia, etapas e mensagens filtradas do FFmpeg.
- Barra de progresso determinada e contagem de tempo decorrido; detecção de inatividade distingue entrada e saída.
- Reprodução/áudio aprovados em campo preservados. Causa física da falha da .17 ainda requer teste com os novos contadores.

# Artin Sentinel 0.2.94.17 — Áudio inicial e exportação Cloud

- Áudio SDK se registra antes de iniciar o transporte; habilitar som após início reabre a posição atual com áudio preparado.
- Exportação Cloud via NetSDK para MP4, escolha de incluir áudio, progresso e cancelamento durante recebimento.
- Marcas de corte independem do arquivo atualmente selecionado.
- Validação de vídeo/duração antes de publicar arquivo; falhas e cancelamentos removem temporários.
- Layout, ponte reutilizável e política Cloud 1× preservados. Teste físico pendente.

# Artin Sentinel 0.2.94.16 — Ponte Cloud reutilizável

O túnel Wine do Intelbras Cloud continua compartilhado por DVR/serial e porta de serviço. Enquanto vídeo, áudio ou consulta de gravações estiverem usando a ponte, ela permanece aberta. Quando o último uso termina, inicia uma janela de 180 segundos para reaproveitamento.

Se houver novo acesso nesse intervalo, o mesmo processo e porta da ponte são reutilizados e a contagem de inatividade é cancelada. Quando o último novo uso terminar, começa outro prazo completo de três minutos. Ao expirar, o processo original é encerrado pelo mecanismo de parada já existente. Uma nova ponte aguarda a anterior terminar de fechar, evitando sobrepor inicializações para o mesmo DVR. Uma ponte morta durante a espera é substituída no próximo acesso explícito.

Ao sair do Sentinel, as pontes são encerradas sem aguardar os três minutos, preservando o encerramento limitado do módulo original. Inicializações que falham e processos que nunca ficaram prontos não são mantidos como pontes válidas. Não há pré-conexão automática de todos os DVRs cadastrados, nem alteração em equipamentos acessados diretamente pelo IP.

O prazo usa o monitor já existente de cada ponte; não acrescenta thread de espera ou timer por encerramento. Senhas de DVR continuam no fluxo de acesso do SDK, sem serem adicionadas à chave de reutilização. O uso ativo continua contado por leases protegidos por lock, incluindo consumidores simultâneos.

Reaproveitar a ponte evita sua inicialização repetida. Login da sessão SDK, preparação do decoder e busca do ponto no arquivo ainda podem levar tempo; o ganho físico deve ser medido no computador de uso.

## Atualizar e testar

Feche o Sentinel, extraia e execute `bash install.sh` como usuário comum. Configuração, SDK e ponte Wine válidos são reutilizados.

1. Abra uma câmera Cloud e observe o tempo até a imagem.
2. Feche o último canal e reabra o mesmo DVR em menos de três minutos. Compare o tempo. A ponte deve ser reaproveitada; ainda pode haver preparação da sessão de vídeo.
3. Mantenha um canal aberto por mais de três minutos: a ponte não deve fechar por causa desse prazo.
4. Feche todos os usos daquele DVR e aguarde mais de três minutos. O próximo acesso deverá abrir uma ponte nova.
5. Confira também consulta de gravações e fechar o Sentinel durante a espera. Nenhum recadastro é necessário.

## Testes de versão

As 27 comparações históricas que exigiam literalmente 0.2.94 agora usam a versão independente do pyproject.toml por fixture. A verificação antiga do instalador também usa essa versão. O teste central continua comparando pyproject.toml, pacote Python e NEW_VERSION do instalador. As verificações de recursos, AKDB, canais e comportamento desses testes foram preservadas.

## Pendências

Visual e régua mantidos. Áudio gravado aguarda o TXT de Configuração → Painel técnico após tentativa de ouvir uma gravação Cloud. Exportação MP4 via Cloud ainda indisponível; recorte entre vários arquivos e feedback de progresso ficam para a próxima etapa. Cloud permanece em 1× e zoom pelo scroll continua adiado.

Installer Fedora/Mint/Arch x86-64 e payloads preservados. Sem instalação física desta .16 ou teste do SDK original em DVR real no ambiente de build. Piloto privado.


---

# Artin Sentinel 0.2.94.15 — Carregamento na janela da câmera

No monitoramento ao vivo, cada câmera mostra uma barra ciano animada enquanto conecta ou reconecta. A barra fica dentro da área da imagem e desaparece quando chega um quadro válido, quando o processo encerra/falha ou quando o operador para/fecha o canal. Não aparece em janela vazia ou quando não há URL/credencial para iniciar uma sessão.

Disponível no mosaico principal e nas janelas independentes. Cada câmera tem estado próprio; mover canais entre janelas preserva o indicador. A barra acompanha o tamanho da janela, sem reduzir a área de vídeo ou bloquear cliques, duplo clique, zoom da câmera ou fechamento.

Usa atualização de estado já existente. Não adiciona timer, thread, consulta ao DVR, login, decoder ou processamento do vídeo. O widget de barra só é criado quando aquela janela começa a carregar e é reutilizado em reconexões; sua animação fica oculta quando não é necessária. Não mostra porcentagem fictícia.

## Atualizar e conferir

Feche o Sentinel, extraia e execute `bash install.sh` como usuário comum. Configurações, equipamentos e ponte Cloud válida são reutilizados.

1. Abra uma câmera no monitoramento: conferir barra durante conexão e desaparecimento com a imagem.
2. Abra duas câmeras: a chegada de uma imagem não deve encerrar a barra da outra.
3. Teste fechar/parar um canal em conexão e, quando aplicável, reconectar; testar também janela independente.
4. Redimensione o mosaico e mova um canal entre janelas; a barra deve acompanhar a câmera.

Visual e fundos corrigidos da .14, régua 5/15/60 e indicadores de Reprodução preservados. Cloud continua em 1×; áudio gravado continua em investigação e zoom da régua continua adiado. Sem instalação física desta .15 em Fedora/Mint/Arch no ambiente de build; installer e payloads existentes mantidos. Piloto privado.


---

# Artin Sentinel 0.2.94.14 — Fundos dos textos

Corrige os retângulos escuros atrás dos textos nos painéis: rótulos comuns agora têm fundo transparente e acompanham a superfície em que estão. A causa era a regra global de fundo para QWidget, herdada também pelos QLabel. A nova regra específica não remove fundos explícitos de cabeçalhos de vídeo, badges e avisos.

Paleta ciano, régua 5/15/60, indicadores de carregamento, layout e funcionamento da .13 preservados. Sem novas alterações em vídeo, áudio, Cloud ou instalação.

Feche o Sentinel, extraia o pacote e execute `bash install.sh` como usuário comum. Confira os títulos e informações dos painéis laterais, a barra superior e o rodapé: o texto deve acompanhar o fundo, sem blocos escuros adicionais. Campos editáveis e controles continuam delimitados.

Correção validada por renderização isolada e testes focados. Sem teste físico desta .14 em Fedora/Mint/Arch neste ambiente; instalador e payloads anteriores preservados. Piloto privado.


---

# Artin Sentinel 0.2.94.13 — Paleta azul escuro e ciano

Aplica a direção visual aprovada pelo usuário à interface existente. Fundo azul quase preto (#0B1420), painéis azul grafite (#142333), texto claro (#DCE7F0), destaque ciano (#37C8E8) em navegação, seleção e controles. Gravações disponíveis seguem verdes (#42B983), assim como os estados positivos; alertas e falhas mantêm suas cores semânticas. Identidade do logotipo preservada.

A régua mantém marcas clicáveis a cada cinco minutos, com traços intermediários nos quartos de hora e maiores nas horas cheias. Marcas discretas em cinza azulado, rótulos claros com intervalo regular adaptado à largura e cursor ciano com ponteiro triangular. Tooltip e seleção por clique preservados. A barra flutuante de busca e abertura usa a mesma paleta ciano.

O acabamento usa cores sólidas, bordas e desenho Qt já existentes. Não adiciona desfoque, sombras, brilho animado, timer, worker, conexão ao DVR ou processamento dos quadros de vídeo. A animação indeterminada de carregamento existente continua funcionando. Não foi feito benchmark físico comparativo de desempenho desta versão.

## Instalar

Feche o Sentinel, extraia este pacote e execute `bash install.sh` como usuário comum. Instalação atualizada com configuração persistente e ponte Cloud válida preservadas. Installer Fedora/Mint/Arch x86-64 e payloads anteriores mantidos.

## Conferir

- Navegação selecionada e controles em ciano; textos e controles desabilitados legíveis.
- Régua com traços de 5/15/60 minutos, cursor e ponteiro ciano, períodos gravados verdes.
- Selecionar dia e horário continua mostrando o indicador flutuante; o vídeo mantém a área e a proporção.
- Zoom pelo scroll não foi implementado. Cloud continua em 1× e áudio gravado continua em investigação, sem nova mudança no transporte nesta entrega.

Testes e renderização local isolada documentados em VALIDACAO_0.2.94.13.md. Sem instalação física desta .13 em Fedora/Mint/Arch no ambiente de build. Piloto privado.


---

# Artin Sentinel 0.2.94.12 — Carregamento visível

Ao selecionar o dia ou atualizar a consulta, uma barra flutuante informa que a busca de gravações está em andamento. Se outra consulta ainda estiver terminando, o aviso indica a espera pelo dia selecionado. O indicador desaparece quando a operação termina, inclusive em erro ou validação sem dispositivo/credencial/período válido.

Ao escolher um horário na régua ou mudar a posição da reprodução, o mesmo indicador mostra “Abrindo gravação das HH:MM:SS…”. Ele desaparece com a primeira imagem, quando todas as tentativas falham ou ao parar a reprodução. Na comparação de câmeras, a primeira imagem encerra o indicador geral; as demais mantêm seus próprios estados nos quadros.

A barra é animada e não mostra porcentagem, pois o DVR não informa progresso confiável. É um elemento dentro da área de vídeo, sobreposto sem reduzir seu espaço ou bloquear os cliques, sem janela modal ou event loop aninhado. A interface continua utilizável. Usa o ciclo de atualização já existente da reprodução; não acrescenta worker, consulta de rede ou timer próprio.

## Instalar e testar

Feche o Sentinel, extraia e execute `bash install.sh` como usuário comum. A configuração e a ponte Cloud válida são preservadas.

1. Escolha outro dia. Confira o aviso flutuante durante a busca e seu desaparecimento ao concluir, mesmo em dia vazio ou com erro.
2. Escolha um horário com gravação na régua. Confira o aviso com a hora e seu desaparecimento ao chegar a imagem.
3. Durante a conexão, Parar deve encerrar o indicador de abertura. Se houver uma consulta de dia ainda ativa, seu aviso permanece até terminar.
4. Redimensione a janela: o indicador deve permanecer dentro da área de vídeo, sem deslocar os controles.

Régua 5/15/60 e diagnóstico de áudio da .11 preservados. Reprodução Cloud continua em 1× e áudio gravado permanece em investigação, sem correção adicional nesta versão. Installer Fedora/Mint/Arch x86-64 e payloads preservados, sem instalação física desta .12 no ambiente de build. Piloto privado.


---

# Artin Sentinel 0.2.94.11 — Régua de gravações

Régua com traços a cada 5 minutos, destaque intermediário nos quartos de hora e traços maiores nas horas cheias. Rótulos são espaçados conforme a largura disponível para não sobrepor números. O mouse mostra o horário da marca; clicar próximo a um traço (na faixa dos traços) seleciona seu horário exato. Clicar na barra de gravações continua permitindo posição livre. A busca e os limites dos trechos são respeitados: marcação não significa gravação disponível, e lacunas não iniciam vídeo.

No dia completo há 289 marcas, incluindo as duas extremidades. Em janelas estreitas, a precisão do mouse fica limitada pela quantidade de pixels disponível. A cor verde indica disponibilidade informada pelo DVR.

## Estado confirmado em campo

O usuário confirmou continuidade da reprodução da .10 no DVR Cloud. O áudio gravado continua não confirmado no teste físico. A velocidade Cloud continua limitada a 1× no aplicativo; não é uma falha nova da régua nem há liberação de aceleração Cloud nesta versão.

## Diagnóstico do áudio

Foi identificada uma lacuna de observabilidade: a interface lia o status do áudio gravado, mas não consumia seus diagnósticos para o painel técnico. Agora Configuração → Painel técnico registra status e mensagens de áudio, saída tentada, encerramento do processo, limite da fila e expiração do prazo, quando ocorrerem. Isso não é uma correção do transporte/codec do áudio; permite identificar a falha física sem alterar a sessão de vídeo validada.

## Instalar e testar

Feche o Sentinel, extraia este pacote e execute `bash install.sh` como usuário comum. Configuração persistente e ponte Cloud válida são reutilizadas.

1. Escolha DVR/canal/dia, espere os trechos e clique na marca de um horário gravado (por exemplo 09:15). Confira o início nesse horário.
2. Confira traços curtos de 5 minutos, médios de 15 e maiores de hora, além do horário mostrado ao passar o mouse.
3. Ative Ouvir áudio uma vez, aguarde o resultado e salve Configuração → Painel técnico → Salvar diagnóstico. Envie o TXT para investigar a saída/codec/fila. O vídeo deve continuar independente.

Instalador Fedora/Mint/Arch x86-64 e payloads da .10 preservados. Sem instalação física desta .11 nestes sistemas no ambiente de build. Piloto privado.


---

# Artin Sentinel 0.2.94.10 — piloto

A reprodução SDK passa a controlar a fila pela quantidade de pacotes e pelo volume em bytes. Pacotes pequenos podiam atingir o limite de objetos antes do limite em bytes e encerrar a sessão. O teste sintético reproduziu essa interrupção antes da alteração e permaneceu ativo após ela. A causa no DVR físico ainda precisa ser confirmada.

Configuração → Painel técnico mostra etapas de Live View e Reprodução, estado e quadros das reproduções abertas, pausas/retomadas da fila e erros do transporte. Histórico em memória limitado a 1.000 linhas. Copiar e Salvar diagnóstico são ações opcionais. O painel é somente leitura e não executa comandos. URLs e campos de credenciais são omitidos; confira o texto antes de compartilhar.

O layout aprovado da .9 foi preservado. Cloud continua em 1×. Não há nova promessa de velocidade Cloud ou correção de calendário/saúde nesta entrega.

## Atualizar e testar

Feche o Sentinel, extraia esta pasta e execute `bash install.sh` como usuário comum. A atualização preserva a configuração e reutiliza a ponte Cloud quando válida.

1. Abra uma gravação, inicialmente sem som, e deixe tocar por pelo menos dois minutos, sem saltar na régua.
2. Confira depois duas câmeras e o áudio, separadamente.
3. Se parar, abra Configuração → Painel técnico, salve o diagnóstico e informe o horário aproximado. Não precisa recadastrar o DVR.

Sem teste físico desta versão no Fedora, Mint ou Arch neste ambiente. Instalador e payloads multiplataforma existentes preservados. Distribuição de teste privado.


---

# 0.2.94.9 — Reprodução compacta (piloto)

- Seleção DVR/canal/dia em linha, consulta automática e régua do dia.
- Tabela de trechos na lateral direita recolhível; recorte recolhível.
- Corrige reserva de células ocultas no player e redimensiona o quadro sem exigir nova mídia.
- Configuração: quatro ações superiores em uma linha.
- Instrumentação do atraso da GUI e callbacks Live/Reprodução no relatório do PC.
- Preserva sessão compartilhada de áudio da .8; validação física pendente.

# 0.2.94.8 — Áudio gravado e desempenho (piloto)

- Escuta gravada SDK deriva da conexão de vídeo, com buffer independente limitado. Não abre segundo login/playback.
- Diagnóstico local de 30 segundos: CPU total e do Sentinel/descendentes, RAM, quadros recebidos e perfis.
- Estimativa conservadora da mistura atual, sem número quando o perfil muda ou a entrega de quadros é insuficiente.
- Aviso de pressão sustentada de CPU/RAM, sem fechar ou alterar canais.
- Preserva calendário e correção de reuso Cloud do instalador .7 revisão 2.

# 0.2.94.7 — Calendário integrado (piloto)

- Painel de disponibilidade substitui o calendário simples de Início/Fim.
- Consulta automática do mês por canal, cache de 12 horas e cancelamento da consulta anterior ao navegar.
- Seleção do dia inteiro e localização da mais antiga no mesmo painel.
- Cancelamento em rede não persiste falso erro no dia interrompido.
- Áudio de gravação Cloud continua com falha de campo pendente. Áudio ao vivo, pesquisa por datas e ritmo normal 1× confirmados pelo usuário na base .6.

# 0.2.94.6 — Histórico e ritmo de reprodução (piloto)

- Reprodução SDK recebe ritmo de leitura e pausa/retomada quando há acúmulo; vídeo ao vivo mantém seu caminho.
- Histórico por canal com calendário e cache de 12 horas, sem credenciais no cache.
- Busca de dia inteiro e localização da gravação mais antiga dentro do intervalo escolhido.
- Consultas sequenciais, cancelamento entre etapas, parada após rejeição de credencial ou três falhas consecutivas.
- Cloud permanece em 1× com seletor desabilitado. Requer validação física antes de publicação Stable.

# 0.2.94.5 — Recording Search + Native Intelbras Speed Hotfix

- Corrige Buscar gravações desabilitado no Cloud por exigir uma interface Web.
- Corrige a mesma condição ao terminar a consulta, permitindo buscar novamente.
- Velocidades locais Intelbras de 0,5× a 16× usam NetSDK em processo isolado, login local modo 0 e CLIENT_SetPlayBackSpeed.
- Mapeamento de velocidade conferido no header original. Falha do comando é informada e encerra a sessão sem anunciar aplicação bem-sucedida.
- Mantém RTSP local em 1×, transporte de exportação anterior e restrição Cloud a 1×.
- Áudio de gravação acelerada segue o mesmo comando nativo, com atempo no player local; depende do áudio enviado pelo DVR.
- Não altera descoberta, cadastro, Main/Sub e política do instalador Fedora/Mint/Arch.

# 0.2.94.4 — Cloud Media Pilot

- Main/Sub real no SDK, perfil ativo e fallback apenas no modo Automático.
- Migração local de canais 0.2.94.3 sem recadastro ou alteração das preferências.
- Escuta pelo SDK isolado, confirmação por áudio decodificado, controle de volume existente e túnel compartilhado com o vídeo.
- Busca de gravações e reprodução por horário em 1×; nenhum caminho HTTP/RTSP externo é presumido.
- Classificação de gravador Cloud preenchida; modelo continua não confirmado quando não há evidência.
- Diagnóstico com tempo até túnel disponível e primeiro quadro.
- Instalação completa para Fedora/Mint/Arch, preservando o perfil existente.
- Novas mídias dependem de teste físico; exportação Cloud, velocidades adicionais e talkback pendentes.

# 0.2.94.3 — Intelbras Cloud via Wine (piloto)

- Cadastro Cloud automático via Wine, mantendo a ponte externa anterior.
- Um processo de túnel por DVR/porta de serviço, compartilhado entre os canais.
- Porta local dinâmica, cancelamento e encerramento com Cleanup antes da terminação limitada por prazo.
- Recursos C# incluídos no pacote Python; compatibilidade de compilação com referência .NET 4.0.
- Preparação por usuário para Fedora, Mint/Ubuntu e Arch x86-64.
- Kit privado completo importa NetSDK apenas se não houver SDK instalado; atualização preserva os dados.
- Teste de campo da integração segue pendente. Vídeo pelo caminho Wine foi confirmado no Mint com o probe 1.4.3.

# Artin Sentinel 0.2.94.2 — Intelbras Cloud Bridge Pilot

- Consumo do túnel SIM Next no mosaico, com NetSDK em processo isolado.
- Cadastro por serial esperado e endpoint local; credenciais no cofre ou em memória.
- Inventário e confirmação de vídeo separados; limpeza e reconexão limitadas.
- Piloto assistido pela VM; não constitui abertura Cloud autônoma no Linux.

# Artin Sentinel 0.2.94.1 — Menu Selection UX

- **Menus e submenus:** a opção sob o cursor recebe destaque forte, deixando claro qual ação será executada ao clicar.
- **Seleção persistente:** opções marcadas/checked usam um estado visual próprio e continuam distinguíveis do simples hover.
- **Listas suspensas:** QComboBox e respectivas listas usam o mesmo padrão de hover/seleção, com contraste consistente.
- **Itens desabilitados:** ficam visualmente separados das ações disponíveis, reduzindo interpretação equivocada.
- Alteração exclusivamente de UX/estilo; não modifica protocolos, descoberta, vídeo, áudio, PTZ, banco ou lógica operacional.

# Artin Sentinel 0.2.94 — Live View Resilience & Audio Controls

- **Live View:** fechar uma câmera maximizada restaura o mosaico e recriar a grade limpa também os tiles ocultos. Callbacks atrasados e sessões canceladas não reabrem canais fechados. Watchdog detecta decoder ativo sem frames e recupera somente o canal afetado, com backoff e pausa retomável após falhas repetidas.
- Encerrar o aplicativo cancela retries/timers e aguarda a limpeza de workers, players e processos de mídia. Uma falha em um canal não reinicia os demais.
- **Áudio de escuta:** curva perceptual torna níveis baixos e médios mais utilizáveis; 0% permanece mudo e 100% mantém o máximo normal. Trocas de canal/Main/Sub aguardam a limpeza do player anterior, e a interface mostra rótulo e percentual atualizados.
- **Microfone/talkback:** ganho independente ajustável entre 50% e 200%; 100% preserva o nível original e o limitador protege contra picos antes da codificação. O percentual, reset para 100% e botão “Testar” ficam visíveis. Stop continua associado à sessão/canal original após trocar a seleção; diagnósticos permanecem sanitizados.
- **UX:** removido o zoom duplicado do inspector; o zoom no quadrante e a capability do backend foram preservados. As linhas Áudio/Microfone se adaptam a larguras menores; seletor NetSDK e nomes longos permanecem dentro do painel.
- IT-Blue continua no caminho DVRIP/Sofia; MiboCam iMX-C continua no NetSDK. Os modos B/C da MiboCam não são declarados homologados e não foram anunciados protocolos novos. Capacidades podem depender de validação física por modelo.
- **Validação de campo:** controles Áudio/Microfone foram conferidos visualmente; IT-Blue foi usada em vídeo, áudio/talkback e estabilidade; MiboCam foi usada no layout e controles NetSDK/talkback. Hikvision não foi validado fisicamente por indisponibilidade do equipamento e continua pendente. A investigação de eventos/detecção/luz/sirene da IT-Blue não faz parte desta versão.
- A suíte automatizada e a consistência entre as fontes de versão acompanham a release.

# Artin Sentinel 0.2.93 — PTZ, Stream Diagnostics & Channel Health

- PTZ usa capabilities e providers comprovados, evita inferências genéricas, preserva alvo, direção e velocidade originais para Stop, encerra o movimento ao trocar/fechar a seleção e descarta resultados atrasados associados a outra seleção.
- Diagnóstico Main/Sub cobre somente rotas cadastradas e informa codec/resolução de vídeo, faixas de áudio disponíveis e causas distintas de falha. Cancelamento não persiste resultados parciais.
- Saúde por canal reduz alertas repetidos, trata transições SEM SINAL/OFFLINE e sinaliza RECUPERADO na primeira confirmação saudável, preservando o histórico.
- Talkback consolida prontidão das rotas existentes DVRIP/Sofia, Intelbras HTTP postAudio e Intelbras NetSDK, com mensagens de dependências ausentes e sanitização de credenciais conhecidas.
- Validação física informada: MHDX 1004 e câmeras IP/MiboCam disponíveis foram usados, sem problemas aparentes nos fluxos verificados. Hikvision não foi validado fisicamente por indisponibilidade do equipamento; a validação específica permanece pendente.
- ONVIF genérico não habilita PTZ automaticamente; equipamentos atrás de gravadores não recebem capability de talkback por inferência. Não são anunciados protocolos ou compatibilidades novos.

# Artin Sentinel 0.2.92 — Acesso Web confirmado e gestão de equipamentos

- A descoberta sonda HTTP e HTTPS separadamente e registra confirmação e histórico de falhas por endpoint. Porta TCP aberta e `web_url` legado continuam sendo apenas pistas.
- O acesso Web só fica disponível quando há confirmação HTTP. Vários serviços podem ser selecionados; HTTPS confirmado tem preferência e o endereço aberto contém apenas IP, esquema e porta, sem credenciais.
- A tela Configuração → Equipamentos separa cadastrados e descobertos, aproxima as ações da tabela correspondente e agrupa Canais e Excluir da descoberta em Mais.
- O cadastro manual mantém os valores e o diálogo aberto quando a validação falha; o contador da tabela mostra os resultados visíveis em relação ao total.
- A suíte automatizada cobre armazenamento, probe e integração Qt; as três fontes oficiais de versão são verificadas quanto à consistência.

# Artin Sentinel 0.2.91 — Configuração e descoberta

A aba Atualizações permite rolar verticalmente sem esmagar os campos. Equipamentos cadastrados continuam visíveis após a inclusão e após nova busca, com a marca * Incluído. Selecione a linha para ler Canais ou Excluir com a confirmação existente. Ver incluído seleciona o cadastro anterior. Equipamentos arquivados permanecem identificados para restauração.
