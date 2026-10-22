# Artin Sentinel 0.2.94.32 — roteiro conjunto

## Instalação

Feche o Sentinel. Extraia o ZIP e rode `bash install.sh` como usuário normal.
O instalador mantém o runtime e os cadastros existentes, incluindo Intelbras.
Fedora, Mint/Ubuntu e Arch mantêm os caminhos de instalação por distribuição.
Não é preciso excluir ou cadastrar novamente os DVRs. Esta build exige teste físico;
aqui não houve acesso à rede ou ao DVR do usuário.

## 1. Componentes e diagnóstico

Em Configuração abra **Componentes e SDKs…**. Confirme FFmpeg/FFprobe/FFplay,
codecs, Wine, NetSDK Intelbras, HCNetSDK Hikvision e o prefixo da ponte Cloud.
Ausente, Disponível, Carregamento OK e sessão funcionando são estados distintos.
A carga das bibliotecas ocorre em subprocessos com prazo; não faz login em DVRs.
Versões nativas são mostradas em hexadecimal quando o SDK anuncia o valor.
O registro aceita novos verificadores conforme novos componentes forem integrados.
Não instala automaticamente SDKs desconhecidos nem presume que todo plugin do
sistema foi integrado. A presença do prefixo Wine não prova túnel ativo.
Use **Verificar novamente** e **Copiar diagnóstico**.

Em **Diagnóstico e atividade…**, copie o log após um problema. Avisos repetidos de
atraso do FFmpeg são agrupados, evitando apagar rapidamente os erros de exportação.

## 2. Hikvision existente — confirmar o acesso

Selecione Hik16 em Equipamentos. Em **Editar → Acesso Hikvision / SDK…**, importe
se necessário a mesma pasta extraída do HCNetSDK Linux x86_64 usada nos testes.
Ative SDK para pesquisa/reprodução; para Ao Vivo marque também a opção própria.
Porta 8000, mapa `1=1` para a câmera analógica testada. Salve.
A confirmação orienta reabrir o canal e refazer a pesquisa. Resultados antigos são
limpos ao salvar, para não reutilizar uma rota RTSP de uma pesquisa anterior.
Não inferimos o índice SDK de câmeras IP; elas precisam de mapa confirmado.

Abra o canal em Main e compare data/hora com o navegador/monitor físico. A prévia
Hikvision Main agora usa 1280×720, mantendo até 10/20 FPS conforme perfil; não
promete resolução nativa superior. A inscrição mostra codec e resolução recebidos,
além do acesso real. O redimensionamento continua preservando a proporção da mídia.
Outras marcas conservam o tamanho anterior da prévia. O nome amigável não é colorido;
a inscrição técnica pode usar a cor do fabricante definida na AKDB.

## 3. Reprodução e aceleração

Atualize o dia 21/10/2026, canal 1; use o trecho da noite com imagem real, não o
arquivo da manhã que contém a tela sem vídeo. Teste 1× por um minuto, depois
2×, 4× e 8× e retorno a 1×. Observe o relógio gravado e o avanço medido.
A aceleração SDK envia PLAYNORMAL/PLAYFAST ao DVR; aceite do comando não comprova
velocidade real nem desempenho. Trocar velocidade reabre no cursor atual.
Se o DVR recusar, a sessão informa erro; não afirma aceleração bem-sucedida.
O antigo caminho Hikvision RTSP/ISAPI fica em 1×, porque acelerar apenas a leitura
local não demonstrou acelerar o fluxo desse DVR. Os controles Intelbras são preservados.
Substream, áudio de escuta Hikvision SDK e Cloud Hik-Connect continuam pendentes.

## 4. Exportação

Marque inicialmente um trecho curto de 30–60 segundos com imagem. Exporte Original,
depois Compacto, com e sem áudio quando o trecho realmente contiver áudio.
A exportação SDK usa o fluxo nativo; Original copia o vídeo e converte áudio para
AAC quando incluído. Compacto usa H.264 até 720p/15 FPS com bitrate reduzido.
A taxa de entrega depende do DVR; esta build não promete download acelerado.
O modo Original não recodifica o vídeo. A prévia é interrompida durante a exportação.

A conclusão exige MP4 com vídeo e duração compatível com o corte. Um EOF sem erro
não é suficiente. Há watchdog e cancelamento, captura sanitizada do erro do FFmpeg,
verificação da duração por FFprobe e confirmação com caminho/tamanho do arquivo.
Uma tolerância de até 2 segundos cobre limites de quadros/contêiner. Arquivos sem
cobertura suficiente não são publicados. Falhas nativas interrompem a publicação;
fechamento do pipe após o FFmpeg atingir o corte só é aceito com duração validada.
Destinos sem suporte a hard link usam criação exclusiva; arquivos existentes não
são sobrescritos. A escrita alternativa não é atomicamente visível durante a cópia.

O erro exato da exportação anterior não constava no relatório de campo; portanto
os ajustes não são apresentados como causa confirmada daquele caso. Testar o novo
corte e guardar o diagnóstico se falhar novamente.

## 5. Cadastro e menus

Adicionar reúne equipamento local/VPN e Intelbras Cloud. No cadastro local, marca
vem primeiro, com orientação de compatibilidade e referência AKDB. A marca sugere
protocolo; modelo, canal e teste real continuam necessários. Para novo gravador
Hikvision com runtime presente, a opção de preparar SDK abre a configuração já
pré-selecionada; ativação só é salva após confirmar o mapa. Cancelar não ativa SDK.
Cadastros existentes não são migrados silenciosamente.

Canais reúne consultar e atualizar. Diagnóstico oferece somente testes de fabricante
compatíveis com a seleção. Credenciais ficam em Editar; ações raras ficam em Mais.
Arquivar e excluir permanecem ações distintas. A seleção manual de protocolo é
preservada quando diverge da sugestão automática de marca.

## 6. Regressão Intelbras

Confirme Ao Vivo local e Cloud, áudio já validado, régua, velocidades e exportação.
Não alteramos a implementação da ponte nem seus parâmetros de vídeo. O log FFmpeg
passa a permitir leitura de metadados de entrada; os avisos de velocidade são limitados.
O exportador Cloud existente mantém seu caminho próprio.
