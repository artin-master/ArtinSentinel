# Artin Sentinel 0.2.85 — Destaque da câmera

Em Equipamentos → Buscar / atualizar → Detalhes da busca, a varredura distingue endereços avaliados, hosts com serviços, possíveis CFTV, outros hosts e equipamentos já conhecidos/ignorados. Marca HTTP ou porta 8000 isolada não bastam para chamar um modem/AP de CFTV; RTSP na porta 554 é candidato sem classificação automática como câmera. A coluna Evidência mostra as razões da identidade AKDB.

Registros oficiais novos da AKDB compartilhada com domínio Sentinel entram na identificação de modelos. A identificação ainda exige evidência forte e preserva overrides manuais. Serviços genéricos e registros apenas de outros apps não tornam um host câmera automaticamente. Valide em uma rede real antes de considerar a regra homologada.

Na Saúde, uma consulta RTSP sem resposta, 401 ou 503 não prova câmera sem sinal/offline. O canal passa a **INCONCLUSIVO**, e canais de equipamentos inteiros offline são exibidos separadamente. Após instalar, aguarde uma nova rodada de monitoramento (aproximadamente 30 segundos) para revisar estados anteriores.

Para perfis de modelo já conhecidos, uma extensão Sentinel **oficial** mais nova na AKDB compartilhada pode atualizar capacidades operacionais, como quantidade de canais, áudio e protocolos. Um ajuste manual de capacidade no gravador continua prevalecendo. Evidências candidatas de campo não alteram o perfil automaticamente; modelos novos ainda exigem catálogo/assinatura de identidade no app.

A interface usa base azul escura e acentos verdes mais claros, inspirados na harmonia do ANL. Os controles de reprodução têm fundo neutro; as cores indicam a função nos próprios ícones, inclusive nas tesouras de corte.

Na Reprodução, os ícones usam cores por função e os botões de corte exibem tesouras: verde para início, azul para fim, vermelho para parar, azul para saltos e dourado para exportar MP4. As dicas ao passar o mouse explicam cada ação.

No monitoramento ao vivo, layout e ações do mosaico aparecem em um grupo compacto. O botão do painel de controles usa ícone e indica visualmente quando o painel está aberto. Os ícones têm contraste uniforme e dicas ao passar o mouse.

Sobre uma imagem ao vivo ou gravação: gire a roda do mouse para ampliar até 8× ou reduzir, arraste para mover a área ampliada e clique com o botão direito para restaurar. É zoom digital sobre os pixels recebidos; a nitidez depende do stream e da gravação. O duplo clique mantém sua função de destaque da câmera.

A senha local agora pode ter a partir de 4 caracteres. Senhas já criadas continuam válidas; a alteração está em Configuração → Alterar senha de acesso.

O seletor de velocidade oferece 0,5×, 1×, 2×, 4×, 8× e 16×. Velocidades altas exigem mais do gravador, da rede e do PC; use os saltos de tempo para localizar rapidamente um horário.

Na primeira abertura, crie a senha local (mínimo de 4 caracteres). Ela será exigida ao iniciar e ao fechar pela janela. Para trocar: Configuração → Alterar senha de acesso. Guarde a senha; não há recuperação automática. A proteção controla a interface do app e não substitui a proteção da conta do sistema operacional nem impede que o sistema encerre o processo à força.

Na reprodução, dois cliques sobre uma câmera ampliam seu quadro dentro da área de vídeo; outros dois cliques restauram o mosaico. As demais câmeras continuam reproduzindo enquanto estão ocultas.
Os botões ↶/↷ saltam 30 segundos ou 5 minutos, e a linha do tempo permite clicar no horário desejado. Cada salto reconecta ao trecho naquele horário; a resposta depende do gravador e da rede.

Na aba **Reprodução**, os filtros e trechos ficam à esquerda e o vídeo à direita. Escolha um gravador Intelbras, um canal e um período de até 24 horas. **Buscar gravações** lista os arquivos e desenha blocos verdes nos horários em que há gravação. Passe o cursor sobre a faixa para ver a hora exata ou clique em um bloco para iniciar nesse instante. A barra do trecho também informa a hora sob o cursor. Use **Marcar início** e **Marcar fim** para selecionar somente a parte que deseja salvar; **Baixar MP4** converte esse intervalo em segundo plano para H.264/AAC. Veja `docs/INTELBRAS_PLAYBACK_LAYOUT_0263.md`.

Para comparar câmeras do mesmo gravador, marque **Comparar até 4 câmeras**, selecione os canais e faça a busca. A faixa mostra uma linha por câmera; clicar em um horário abre as câmeras com gravação disponível naquele ponto. O controle de velocidade oferece 0,5×, 1×, 2× e 4×. A busca da CAM 2 em diante foi corrigida para o índice de resposta observado no MHDX. A comparação sincroniza o horário solicitado, com possíveis diferenças de chegada dos quadros pela rede. Exportação MP4 e marcadores de corte permanecem no modo de um canal. Veja `docs/INTELBRAS_MULTICHANNEL_PLAYBACK_0264.md`.

Em **Atualizações**, configure a URL base HTTPS da sua origem privada e salve uma chave individual de cliente em **Acesso privado**. O manifesto e o pacote são obtidos com essa chave; o pacote deve usar o mesmo servidor. Chaves ficam no cofre do usuário; a instalação ainda exige confirmação e verifica SHA-256. Consulte `docs/PRIVATE_UPDATES_PILOT_0259.md` para preparar a origem no seu PC e conectá-la a um servidor externo. **Sem domínio, HTTPS e túnel externos configurados, não há atualização remota disponível.** A primeira instalação desta versão é manual.

Em **Ao vivo**, o botão **Controles** recolhe ou mostra a lateral direita para ampliar o mosaico; a escolha é preservada ao reiniciar. Na árvore à esquerda, gravadores começam recolhidos e cada expansão ou recolhimento é lembrado. Uma busca temporária pode expandir resultados, sem mudar a preferência salva.

O botão **Abrir gravações no navegador** continua disponível como alternativa para consultar diretamente o gravador.

Na aba **Equipamentos**, escolha o Site ativo no topo. **Gerenciar Sites** expande as ações de renomear, arquivar, restaurar e excluir. A antiga aba Sites foi integrada a este painel; equipamentos continuam vinculados ao respectivo Site.

**Logs e diagnóstico** permanece recolhido até ser aberto. Consulte canais do Site, leitura RTSP, diagnóstico da sessão ao vivo, atualizações e falhas; use Atualizar e o filtro para localizar erros. O painel mostra uma amostra limitada dos arquivos e oculta segredos conhecidos. Confira o texto antes de compartilhá-lo, pois pode conter endereços da rede. Para o NVD 1416, leia novamente os canais e confira o estado em **Canais do Site** e **Leitura RTSP**.

Ao executar `./install.sh` para instalar ou atualizar, se o Sentinel estiver aberto, o instalador pede para fechar suas janelas e aguarda uma nova verificação com **Enter**. Em execução sem terminal, interrompe a instalação com uma mensagem clara para fechar o aplicativo e repetir; `--yes` confirma apenas pacotes do sistema e não dispensa o fechamento. **Nenhuma atualização do runtime começa com o aplicativo aberto.** `./install.sh --check` continua somente leitura e não pede fechamento. Pelo centro de atualizações, a janela atual é fechada automaticamente após a confirmação, e qualquer outra instância aberta impede a instalação. Veja `docs/INSTALLER_CLOSE_GUARD_0257.md`.

## Histórico da 0.2.56

Os NVD 1416 e 1516 podem listar 16 posições de canais mesmo quando ainda não entregam imagem. Na leitura Intelbras de NVRs, o Sentinel agora exige que o FFmpeg receba e decodifique **um quadro real via RTSP/TCP** antes de marcar um canal como disponível. O resultado sem imagem permanece no inventário, com a causa resumida em **Canais / Stream → Evidência**. Se a autenticação RTSP não for confirmada, a janela identifica corretamente o gravador e informa se o teste HTTP também respondeu 401. O mosaico não abre em massa posições NVR sem vídeo confirmado. O comportamento já validado do MHDX 1004 permanece como estava. Isso identifica melhor a falha, mas não corrige por si só credenciais, câmera desconectada, porta RTSP, codec ou configuração do gravador. Veja `docs/NVD_VIDEO_DIAGNOSTICS_0256.md`.

## Histórico da 0.2.55

Na aba **Configuração → Equipamentos**, use **Buscar / atualizar** para localizar novos equipamentos. Selecione um resultado para **Adicionar selecionado**, **Relatório AKDB** ou **Web do encontrado**. O botão Web fica ativo somente quando a busca detecta HTTP/HTTPS no IP daquele dispositivo; a página abre no navegador padrão e a senha continua fora do endereço. **Detalhes da busca** exibe as evidências e erros. Os dispositivos já cadastrados mantêm o botão **Web**. A antiga aba Descoberta foi removida; os atalhos levam à aba Equipamentos. A detecção de uma porta Web não garante que o equipamento permita configuração por navegador.

## Histórico da 0.2.54

A aba **Configuração → Equipamentos** agora reúne a busca na rede e os equipamentos cadastrados, com ações **Buscar / atualizar** e **Adicionar selecionado**. A tabela de cadastrados mostra posições listadas e canais cujo vídeo foi confirmado. A leitura Intelbras usa automaticamente o limite do modelo na AKDB (MHDX 1004: cinco; NVD 1416, NVD 1516 e MHDX 1216: 16), corrigindo limites antigos de cinco quando o modelo é identificado. Ajustes manuais continuam por gravador. Para muitos canais, o prazo de verificação RTSP é proporcional à capacidade; ao esgotar, as posições pendentes aparecem para diagnóstico e os canais já validados permanecem disponíveis. Uma posição listada pela AKDB não confirma vídeo.

## Histórico da 0.2.53

Esta versão impede que um instalador anterior substitua uma versão mais recente já instalada. `./install.sh --check` mostra a versão instalada, diagnostica dependências sem alterar o aplicativo e retorna erro se faltar vídeo. Para retornar intencionalmente a uma versão anterior, é preciso informar `--allow-downgrade` ao instalador desta versão ou posterior; pacotes antigos que ainda não têm essa proteção devem ser evitados. Se a 0.2.41 substituiu a 0.2.49, execute o instalador desta versão para recuperar o aplicativo e suprir FFmpeg e codecs necessários para o Live View.

## Histórico da 0.2.52

Esta versão verifica no computador novo os programas FFmpeg, os decodificadores H.264/H.265, a leitura RTSP, a conversão de um quadro RGB24 e a inicialização de Qt/PySide6. Execute `./install.sh` em um terminal ou `./install.sh --yes` para aceitar os pacotes do sistema; `./install.sh --check` apenas diagnostica e retorna erro se faltar um requisito de vídeo. No Fedora, se o repositório de codecs já oferecer `libavcodec-freeworld`, o instalador o inclui. SDKs dos fabricantes continuam opcionais e importadas na interface.

## Histórico da 0.2.51

Esta atualização corrige a leitura limitada a cinco canais em gravadores Intelbras que receberam o perfil do MHDX 1004 por associação genérica ao fabricante. **Canais / Testar stream** permite escolher e salvar por gravador quantas posições verificar (1–64). Os NVD 1416, NVD 1516 e MHDX 1216, cujas interfaces indicam 16 canais, sugerem 16; o MHDX 1004 sugere cinco. Posições sem vídeo são identificadas separadamente de streams validados. O instalador inclui as dependências normais e trata SDKs separadamente. Consulte `docs/INTELBRAS_RECORDER_CAPACITY_0251.md`.

## Histórico da 0.2.50

O piloto permite ler o MHDX 1004 em outro local quando um computador Linux próximo ao DVR mantém uma conexão SSH de saída com um servidor intermediário administrado pelo operador. Na estação do Sentinel, outro túnel SSH traz Web, RTSP e serviço Intelbras para portas locais. O DVR continua com as configurações atuais. Veja requisitos, comandos e validação em `docs/SITE_CONNECTOR_PILOT_0250.md`.

**Requisitos externos:** computador ligado na rede do DVR, servidor SSH público sob controle do operador e acesso por chaves nos dois lados. O conector não faz login no Intelbras Cloud pelo número de série. Imagem e áudio fora da rede dependem de teste físico com o MHDX.

## Histórico da 0.2.49

Esta versão inicia o teste de gravadores de outros locais. Em **Configuração → Equipamentos → Adicionar**, selecione **Outro local • rede privada/VPN**, informe o IPv4 ou nome de host alcançável e escolha DVR/NVR/XVR. Use **Diagnosticar**, **Canais / Testar stream** e **Ao vivo** como no equipamento local. A rede privada precisa estar ativa antes da leitura. O cadastro identifica o tipo de acesso, mas não cria a conexão de rede.

**Cloud/P2P do fabricante:** um código de série usado no aplicativo do fabricante não equivale a um endereço RTSP. O acesso por Intelbras Cloud, Hik-Connect e similares requer integração específica e ainda não está disponível nesta versão. Detalhes e sequência de campo: `docs/REMOTE_RECORDER_PILOT_0249.md`.

## Histórico da 0.2.48

Esta revisão reforça a checagem da IT-Blue X3-WE2Q: além da resposta de vídeo, cada canal nativo DVRIP deve entregar um quadro decodificado para comparação visual com a PTZ e as lentes já aceitas. Um canal repetido ou sem quadro comparável não confirma outra lente. A busca conserva as posições 1=PTZ, 2=fixa 1 e 3=fixa 2. A seleção de uma lente fixa oculta os controles PTZ mesmo quando o dispositivo conserva o nome genérico Web Viewer.

**Teste físico:** com a câmera online, abra Configuração → Equipamentos → Canais/Stream da X3, execute novamente a leitura e confira separadamente a cena de cada lente. Depois abra as disponíveis no Ao vivo e mova a PTZ: a imagem das lentes fixas deve permanecer independente, com os comandos PTZ disponíveis só na primeira lente. Uma lente cujo vídeo não possa ser distinguido poderá ficar indisponível após a busca.

A verificação local ainda precisa ser confirmada com o equipamento real. Caso a leitura não encontre as três lentes, anote o resultado mostrado em Canais/Stream.

## Histórico da 0.2.47

A revisão anterior estabilizou as posições das lentes, acrescentou a comparação visual conservadora de rotas RTSP e passou a conferir os canais DVRIP nativos. Também reabre sessões quando uma rota validada muda e preserva rotas antigas quando a busca é cancelada ou falha.

## Histórico da 0.2.46

# Artin Sentinel 0.2.46 — AKDB Contributions

Em **Configuração → AKDB → Revisar candidatos…**, o Sentinel lista os relatórios de campo pendentes. Ao selecionar um, mostra a identidade oficial instalada correspondente, eventuais campos divergentes e o conteúdo sanitizado da proposta. A comparação por fabricante e modelo é indicativa; uma correspondência ambígua deve ser revisada manualmente.

**Exportar proposta…** grava um JSON para conferência e mantém o candidato pendente. **Enviar proposta…** pede confirmação explícita e envia somente o candidato selecionado à caixa de entrada configurada no repositório GitHub. Um token do repositório pode ser guardado no keyring; ele não vai para o arquivo, o banco ou o JSON. O envio registra um candidato para revisão, não publica uma nova revisão oficial da AKDB. O envio automático oferecido em versões anteriores foi desativado inclusive para configurações existentes.

Recomenda-se executar **Verificar AKDB** e aplicar eventuais revisões oficiais antes de comparar candidatos. A exportação usa a base oficial que estiver instalada no momento da revisão. A sanitização retira campos de identificação de instalações e padrões reconhecíveis em observações; antes de exportar ou enviar, confira sempre a prévia, sobretudo em campos de texto livre.

A 0.2.46 preserva a prévia de atualizações da 0.2.45, a aplicação transacional da 0.2.44, a sincronização da 0.2.43 e os recursos do Live View das versões anteriores.

## Reprodução Hikvision (piloto 0.2.70)

Com o gravador acessível por rede privada/VPN, selecione-o na Reprodução e pesquise até quatro canais por vez. A busca usa ISAPI ContentMgmt/search por canal e preserva a URL do segmento devolvida pelo DVR para player e exportação. O horário apresentado usa o fuso do computador; Sites em fuso diferente exigem homologação de horário. Antes de considerar suporte homologado, valide pesquisa, reprodução, busca por horário e áudio/exportação no gravador real.
