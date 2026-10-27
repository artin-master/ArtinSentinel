RELEASE_TITLE = "Equipamentos 2.0 + Titânio/Ciano + Transferência Segura"
RELEASE_NOTES = [
    "Tela de Equipamentos ganha fluxo único para localizar, adicionar e editar, com a descoberta aberta em painel flutuante.",
    "Cadastro e manutenção usam a mesma janela: marca/tipo selecionam o provider adequado e ocultam/bloqueiam acessos incompatíveis.",
    "Salvar um equipamento local já valida a credencial e inicia automaticamente a leitura de canais/stream.",
    "Importação pode transportar credenciais em pacote .asx criptografado com AES-256-GCM + scrypt; senhas são regravadas no cofre local.",
    "Credenciais restauradas são usadas automaticamente para validar acesso/canais, sem pedir novamente a senha de cada DVR.",
    "Identidade visual Titânio + Ciano volta a ser aplicada com escudo e ícones vetoriais próprios em Ao Vivo, Reprodução e Equipamentos.",
    "Hikvision ISAPI/HCNetSDK e Intelbras NetSDK/Cloud da base anterior são preservados; validação física continua obrigatória.",
]
CHANGELOG_TEXT = """Artin Sentinel 0.2.94.38 — Equipamentos 2.0 + Titânio/Ciano

• Dispositivos localizados saem da tela fixa e passam para um painel flutuante.
• Adicionar / localizar centraliza descoberta, inclusão manual e Intelbras Cloud.
• Adicionar, Editar e equipamento descoberto convergem para o mesmo cadastro de acesso.
• A marca/tipo controla quais tecnologias aparecem: Hikvision HCNetSDK/ISAPI/RTSP; Intelbras/Dahua NetSDK/HTTP/RTSP; genérico ONVIF/RTSP.
• Salvar e validar acesso grava o mesmo cadastro, testa credencial e inicia leitura de canais/stream automaticamente.
• Atualizar canais permanece como manutenção manual.
• Exportação pode levar credenciais num .asx criptografado; JSON sem credenciais continua disponível.
• Importação segura restaura credenciais no keyring e reutiliza o cadastro existente sem duplicação.
• Visual Titânio + Ciano restaurado em ícones, marca e estados dos controles.
• Intelbras e Hikvision continuam isolados por provider; motores proprietários não foram substituídos.

Artin Sentinel 0.2.94.33 — Importação Assistida + Hikvision Playback

• Configuração → Equipamentos oferece visão Todos os Sites sem misturar o Site operacional.
• Importações novas ou já existentes são retomadas pelo cadastro original, sem duplicação.
• Equipamentos incompletos entram em configuração pós-importação para credencial e validação de canais.
• A leitura normal por provider é reutilizada; Canais / Stream continua disponível para ajustes posteriores.
• Hikvision ISAPI reforçado com conteúdo de vídeo/metadata explícitos, ResponseStatus sanitizado, track estrito e playbackURI sem credenciais embutidas.
• HCNetSDK Hikvision opcional/isolado da .32 permanece intacto.
• Intelbras/NetSDK, Cloud e demais providers permanecem intactos.
• Validação física ainda necessária antes de promover esta candidata a estável.

Artin Sentinel 0.2.94.30 — Topway IP e estabilidade do Live View

• IDs reais de entradas IP recuperados por InputProxy/channels.
• Referência de protocolo para DEFENDER 16-720T3; marca Topway preservada.
• EOF não é confundido com timeout de 15 segundos.
• Pipes de diagnóstico fechados depois do leitor, reduzindo disputa de descritores.
• Não abre mosaico de entradas analógicas NO VIDEO quando nenhuma está validada.
• Sem dependências novas; Fedora, Mint e Arch preservados no instalador.
• Exige teste físico desta build: canal 18, canal 17, Sub/Main e reprodução.

Artin Sentinel 0.2.94.29 — AKDB, fabricantes e cadastro assistido

• Fabricantes com nome padronizado, aliases e paleta de cores local na AKDB.
• Somente a marca recebe cor na árvore principal e janelas adicionais.
• Catálogo por marca, tipo e modelo, com validação por recurso separada do estado geral.
• Referência AKDB preenche campos vazios no cadastro/edição, sem confirmar acesso.
• Descoberta registra origem, confiança e conflitos; identificadores contraditórios não atualizam cadastro conhecido.
• Pesquisa Hikvision com cancelamento, páginas repetidas e resultados parciais de vários canais.
• Sem homologação física nova; gravações Hikvision requerem teste no DVR real.

Artin Sentinel 0.2.94.28 — Hikvision e identificação na árvore

• Busca ISAPI paginada com sessão estável, deduplicação e erros distintos de dia vazio.
• Roteamento de gravações respeita o protocolo selecionado para modelos compatíveis.
• DVR autenticado sem canais permanece cadastrado; inventário anterior preservado.
• Marca ao lado do equipamento, sem confundir fabricante com protocolo.
• Ações de Configurações na mesma linha quando houver espaço; quebra automática.
• Reprodução física Hikvision, áudio, velocidade e exportação pendentes de campo.

Artin Sentinel 0.2.94.27 — Transferência seletiva

• Inventário com escolha de equipamentos e grupos de dados.
• Prévia sem escrita, inclusão somente de novos e preservação de conflitos.
• Comparação por identificadores e endereço, com revalidação e rollback.
• Senhas e rotas de vídeo não são transferidas.
• Reprodução e perfis da .26 preservados; testes de campo pendentes.

Artin Sentinel 0.2.94.26 — Reprodução e perfis de acesso

• Seletor limitado a 8×; 16× retirado por enquanto.
• Troca de velocidade separada de Seek, retomando mídia no cursor atual.
• Perfil comum compartilhado com permissões locais e senha administrativa independente.
• Controle opcional, desligado na atualização até configuração explícita.
• Cadastro/edição, reprodução, gravação e exportação protegidos nas ações.
• Escuta e exportação de áudio possuem permissões separadas.
• Navegação pela régua e autenticação reutilizada da .25 preservadas.

Artin Sentinel 0.2.94.16 — Reutilização da ponte Cloud

• Ponte Wine compartilhada permanece disponível por 3 minutos após o último uso.
• Novo acesso dentro do prazo reutiliza a ponte; conexões em uso não expiram.
• Saída do Sentinel encerra as pontes sem aguardar o prazo de inatividade.
• Verificações históricas comparam a versão declarada do projeto, pacote e instalador.
• Visual e transporte de mídia preservados; áudio gravado/exportação Cloud continuam pendentes.

Artin Sentinel 0.2.94.15 — Carregamento por câmera

• Barra ciano dentro de cada janela durante conexão e reconexão do monitoramento.
• Oculta ao receber imagem, falhar ou parar o canal; independente por câmera.
• Disponível no mosaico e em janelas independentes, sem reduzir a área de vídeo.
• Visual, régua e reprodução da .14 preservados.

Artin Sentinel 0.2.94.14 — Fundos dos textos

• Rótulos comuns passam a usar fundo transparente, acompanhando o painel e eliminando retângulos escuros ao redor dos textos.
• Cabeçalhos de vídeo, badges e avisos com fundo próprio são preservados.
• Paleta, régua e carregamento da .13 mantidos.

Artin Sentinel 0.2.94.13 — Azul escuro e ciano

• Paleta sólida azul escuro com ciano em navegação e seleção; verde reservado à disponibilidade e estados positivos.
• Régua com traços de 5 minutos, destaques de 15 e hora cheia, cursor ciano com ponteiro triangular.
• Indicador flutuante com a mesma paleta. Sem novo efeito, timer ou processamento de vídeo.
• Layout e operação da .12 preservados; zoom pelo scroll permanece para depois.

Artin Sentinel 0.2.94.12 — Indicador flutuante de carregamento

• Selecionar o dia mostra busca de gravações em andamento.
• Selecionar horário na régua mostra abertura da gravação até a primeira imagem ou falha.
• Barra animada sem porcentagem fictícia; não bloqueia a interface.
• Régua 5/15/60, reprodução e diagnóstico da .11 preservados.

Artin Sentinel 0.2.94.11 — Régua 5 / 15 / 60 minutos

• Marcas de cinco minutos com destaques de quinze minutos e hora cheia.
• Clique nas marcas seleciona o horário exato; clique nos trechos mantém a precisão livre.
• Diagnósticos de áudio gravado passam ao painel técnico, incluindo saída, prazo e erros.
• Reprodução contínua da .10 preservada. Cloud permanece em 1×; áudio em investigação.

Artin Sentinel 0.2.94.10 — Continuidade da reprodução e painel técnico

• Controle da fila SDK por quantidade de pacotes e bytes para evitar interrupção com pacotes pequenos.
• Configuração → Painel técnico: diagnósticos de vídeo e reprodução, quadros e estados, com cópia e salvamento opcionais.
• Layout aprovado preservado; Cloud continua em 1×.

Artin Sentinel 0.2.94.9 — Reprodução por dia e diagnóstico da interface

Reorganiza a reprodução para dar espaço ao vídeo. Dia escolhido alimenta automaticamente a régua; horários de início/fim permanecem apenas como estado interno da consulta/trechos. Configuração compacta e evidência de atraso da interface no relatório de desempenho, sem declarar a lentidão resolvida.

Artin Sentinel 0.2.94.8 — Áudio gravado e capacidade do PC

Reprodução SDK com áudio derivado da mesma conexão. Diagnóstico local do PC, estimativa limitada ao perfil medido e aviso de pressão sustentada. A estimativa não homologa quantidades nem confirma aceleração por GPU.

Artin Sentinel 0.2.94.7 — Calendário integrado

Substitui o calendário simples de Início/Fim pelo painel de disponibilidade. Consulta automática sequencial por mês, cache e troca de mês com cancelamento cooperativo. Sem confirmação extra para consultar o mês do DVR/canal já selecionados.

Artin Sentinel 0.2.94.6 — Histórico e ritmo de reprodução

Controle de leitura do FFmpeg na reprodução SDK e controle de fluxo nativo. Histórico com cache de até 12 horas por dispositivo/canal, consultas diárias e evidência de ausência separada de falhas. A busca da gravação mais antiga é limitada ao intervalo escolhido; não afirma o limite absoluto de retenção.

Artin Sentinel 0.2.94.5 — Recording Search + Native Intelbras Speed Hotfix

Remove a exigência de Web para busca pelo SDK Cloud. Velocidade local Intelbras passa a ser solicitada no SDK, com enums do header original e diagnóstico de aceitação/recusa; 1× e exportação mantêm os caminhos anteriores. As correções precisam de validação física no DVR.

Artin Sentinel 0.2.94.4 — Cloud Media Pilot

Main/Sub, escuta e busca/reprodução por horário em 1× através do túnel Wine. Migração local de canais existentes e diagnóstico de tempo até túnel/primeiro quadro. Fluxos testados com SDK sintético; novas mídias ainda exigem validação física. Mantém instalador completo Fedora/Mint/Arch.

Artin Sentinel 0.2.94.3 — Intelbras Cloud via Wine (piloto)

Gerenciamento do túnel por DVR, porta local dinâmica, compartilhamento entre canais e encerramento ao fechar o último consumidor. Mantém a opção de ponte externa. Pacote privado de teste com bibliotecas verificadas, instalação/atualização e preparação Wine por distribuição. Sem senhas ou cadastros no pacote.

Artin Sentinel 0.2.94.2 — Intelbras Cloud Bridge Pilot

Vídeo Cloud via túnel SIM Next no mosaico. NetSDK isolado, identidade conferida, inventário separado de vídeo validado. Exige VM e encaminhamento local configurados. Piloto para validação de campo; áudio e reprodução pela ponte pendentes.

Histórico da base:
Artin Sentinel 0.2.94.1 — Menu Selection UX

- O Live View restaura o mosaico ao fechar uma câmera maximizada, limpa tiles ocultos ao recriar a grade e ignora callbacks/processos tardios de canais fechados. Watchdog detecta FFmpeg vivo sem frames; reconexão isolada usa backoff e pode pausar somente o canal afetado após falhas consecutivas.
- Shutdown cancela timers/retries e aguarda a limpeza de players, processos e workers. Stop/Close não provoca reconexão posterior e uma falha não reinicia os demais canais.
- Áudio de escuta usa curva perceptual com níveis baixos/médios mais utilizáveis; 0% continua mudo e 100% mantém o máximo normal. Trocas de canal/Main/Sub aguardam a limpeza do player anterior; rótulo e percentual são exibidos em tempo real.
- Ganho independente do microfone: 50%–200%, 100% preserva o nível original, processamento antes da codificação e limitador contra picos. A interface mostra percentual, reset para 100% e botão “Testar”. Talkback permanece associado ao canal original, Stop controla a sessão correta após troca de seleção e cleanup tardio de captura/transport é aplicado.
- Zoom duplicado removido do inspector; zoom no quadrante e capability do backend permanecem. Controles Áudio/Microfone, seletor NetSDK/PTT e nomes longos cabem em larguras menores.
- IT-Blue continua usando DVRIP/Sofia e MiboCam iMX-C continua usando NetSDK. Modos B/C da MiboCam não são declarados homologados, capacidades podem depender de validação física por modelo e nenhum protocolo novo é anunciado.
- Build de campo usada nos equipamentos disponíveis. Controles Áudio/Microfone conferidos visualmente; IT-Blue usada para vídeo, áudio/talkback e estabilidade; MiboCam usada para layout e controles NetSDK/talkback. Hikvision não foi validado fisicamente por indisponibilidade e permanece pendente.
- A investigação de eventos/detecção/luz/sirene da IT-Blue não faz parte da 0.2.94.1. A suíte automatizada e a consistência de versão acompanham a release.
"""
