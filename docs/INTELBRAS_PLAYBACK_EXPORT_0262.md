# Reprodução Intelbras e exportação MP4 — 0.2.62

## Fluxo

O finder HTTP da seção 4.10.5 da API Intelbras lista os arquivos. A reprodução usa o RTSP `/cam/playback` da seção 4.1.2, com `channel`, `starttime` e `endtime` no relógio local do DVR. Para a porta e o endereço RTSP, o Sentinel prefere o stream principal já cadastrado para o canal; na ausência dele, usa o host Web e a porta 554. Nenhuma operação altera a gravação no equipamento.

Ao selecionar o trecho, o início e o fim são limitados à interseção do arquivo retornado com o período solicitado. O player usa FFmpeg com leitura ritmada. O fim do stream encerra a sessão; não reconecta como o Live View. Arrastar a linha do tempo fecha a sessão e solicita outra reprodução a partir do instante selecionado. O indicador de tempo é aproximado, baseado no relógio da sessão; ainda não há timestamps de apresentação extraídos do decoder. A lista não é reconstruída por atualizações gerais do mesmo gravador.

## Exportação

Baixar MP4 solicita o destino ao operador. Um worker FFmpeg decodifica o stream RTSP e converte vídeo para H.264 e áudio, quando houver, para AAC. Converte primeiro para arquivo temporário no mesmo diretório; somente uma conclusão bem-sucedida publica o MP4 sob o nome escolhido. Cancelamento e falhas removem o temporário. Arquivo existente nunca é substituído. O worker fornece progresso aproximado pela duração reportada pelo FFmpeg. A senha é usada em memória no processo local de decodificação e não entra no nome do arquivo ou diagnóstico exibido.

## Validação de campo

1. Fechar o Sentinel e instalar 0.2.62.
2. No MHDX 1004, buscar uma hora com gravação conhecida, selecionar um trecho e reproduzir; anotar diagnóstico caso não entregue frames.
3. Mover a linha do tempo e confirmar retorno à posição escolhida no relógio do DVR.
4. Baixar um trecho curto para MP4 e abrir o arquivo em um player independente; repetir com cancelamento e conferir ausência de arquivo parcial.
5. Repetir em NVD 1416 e 1516, anotando firmware, porta RTSP e se a busca retorna horário/canal coerentes.

O teste automatizado valida comando, estado e publicação atômica com processo simulado; a entrega de mídia ainda exige hardware real.
