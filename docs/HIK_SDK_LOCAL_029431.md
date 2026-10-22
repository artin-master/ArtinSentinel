# Hikvision SDK local — 0.2.94.31

## Instalação e ativação

1. Feche o Sentinel, extraia o pacote e execute `bash install.sh` normalmente.
2. Em Configuração → Equipamentos, selecione o Hikvision e abra **SDK Hikvision local…**.
3. Clique **Importar pasta do SDK oficial…** e selecione a pasta extraída que contém
   `lib/libhcnetsdk.so` (ou a própria pasta lib). Não selecione o ZIP: esta importação
   usa a pasta já extraída. Componentes e dependências da pasta lib acompanham a cópia.
4. Marque “Usar SDK para pesquisa e reprodução”. Para testar o novo Ao Vivo, marque
   também “Usar também no Ao Vivo”. Serviço 8000 e mapa `1=1` para esta câmera analógica.
5. Salve e reabra o canal. Não exclua o DVR, as câmeras ou as credenciais existentes.

O runtime fica no diretório de dados persistente do Sentinel e é reutilizado em
updates. Depois da importação, não depende da pasta original em Downloads.
Outros PCs precisam importar seu runtime oficial Linux x86_64. Não distribuímos
novas bibliotecas proprietárias dentro deste pacote. Fedora foi validado em campo
nos probes anteriores; Mint/Arch mantêm o instalador existente e precisam de teste
físico com esse runtime. Arquiteturas diferentes de x86_64 não são habilitadas.

## Testes no app

- Ao Vivo: abrir canal 1 em Main, manter movimento por 2 minutos, fechar e reabrir.
  Compare com o monitor físico do DVR. Auto usa Main porque Sub ainda não foi validado.
- Reprodução: selecione 21/10/2026 e canal 1. A pesquisa deverá incluir o trecho
  recente iniciado por volta de 21:15, conforme o estado atual do HD. Clique em
  21:20 na régua e teste por pelo menos 1 minuto, em 1×.
- Pule +5 minutos ou clique em outro ponto realmente gravado. Esta primeira
  integração reabre a sessão SDK por salto; não promete seek persistente neste backend.
- Feche/reabra o app e confirme preservação do SDK, cadastro, senha salva e demais DVRs.
- Desative a opção SDK e confirme o retorno ao caminho RTSP/ISAPI já utilizado.
- Verifique um DVR Intelbras local/Cloud e os equipamentos que já funcionavam em SV.

Não precisa testar Sub agora. No DVR de teste ele entregou zero pacotes em 90 s;
isso permanece pendente, sem concluir codec incompatível. Se selecionar Sub
explicitamente, não haverá fallback oculto, e a ausência de mídia aparecerá no diagnóstico.

## Estado dos recursos

Main pelo SDK e busca de arquivos foram confirmados no Fedora pelos probes.
A reprodução integrada está em validação: aceitação do SDK não prova imagem,
velocidade ou sincronismo. Só 1× é oferecido. O SDK aplica pausa/retomada no servidor
fora do callback para manter a fila limitada quando o decoder está drenando.
Áudio/MIC, exportação e velocidades adicionais por esse SDK ficam bloqueados ou
explicitamente indisponíveis. Os recursos existentes em RTSP/ISAPI/Intelbras não
são removidos. Hik-Connect não foi implementado nesta versão.

## Canais e calendário

O mapa tem o formato número no Sentinel = índice no SDK. Exemplo `1=1`.
Um IP pode usar SDK 33 mesmo aparecendo como D17; não inventamos essa correlação.
Só os canais mapeados usam o novo Ao Vivo. Para a pesquisa SDK, canais sem mapa
retornam orientação, sem tentar outro índice nem outra senha automaticamente.
O calendário mantém cache separado por backend/porta/mapa. Cada busca usa até
24 h, uma chamada de login por canal consultado e limite de resultados/tempo.
Dias não encontrados não significam ausência de todo histórico do HD.
Horários são locais ao DVR; o SDK não modifica o relógio nem a agenda.

## Diagnóstico e limites

Os processos nativos e FFmpeg ficam separados da GUI. O fechamento do canal
cancela o processo, encerra a sessão e, se necessário, termina o processo nativo.
Falha nativa não deve derrubar a GUI, mas pode impedir a confirmação de Cleanup.
Uma chamada de login por abertura, sem loop automático de autenticação.
Usuário/senha chegam ao worker por pipe, fora de argumentos, ambiente, SQLite ou logs.
Serial não é comparado neste transporte; o diagnóstico não anuncia “identidade conferida”.

O app foi testado com biblioteca sintética compilada contra o cabeçalho fornecido,
transporte real entre processos, FFmpeg com vídeo sintético e GUI offscreen.
Esses testes não substituem a validação física desta integração no DVR.
