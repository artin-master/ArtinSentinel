# Leitura dos NVD 1416 e 1516 sem imagem

Os modelos NVD 1416 e 1516 indicam **até 16 posições**, o que não significa que os streams estejam ativos. Na família Intelbras/Dahua o Sentinel lê nomes via CGI quando disponível e consulta Main/Sub por RTSP. A partir da 0.2.56, quando o equipamento é classificado como NVR, cada rota precisa entregar um quadro decodificado em até cinco segundos usando FFmpeg e RTSP/TCP, que é o transporte inicial do Live View. Um SDP com código 200 sozinho não confirma imagem.

A captura de campo da 0.2.54 mostrou NVD 1416 com 0/16 vídeos, resposta RTSP 401 após Digest e tentativa FFmpeg sem sucesso. Outro NVR no mesmo computador abriu 16/16. Esse quadro aponta para autenticação, permissão RTSP, configuração ou variante do firmware naquele gravador; não permite concluir isoladamente que a senha está errada. A 0.2.56 corrige o texto que chamava qualquer gravador de MHDX e, se o teste HTTP também receber 401, apresenta isso separadamente.

## Teste com equipamento real

1. Em **Configuração → Equipamentos**, selecione um dos NVD afetados e clique em **Canais / Stream**. Use o usuário e senha desse mesmo NVD; selecione 16 posições.
2. Na janela de resultados, observe o total **com mídia validada**. Veja a coluna **Evidência** de um canal cuja imagem aparece no próprio gravador. Se o NVD respondeu RTSP sem transmitir um quadro, o canal ficará listado, mas não será anunciado como vídeo confirmado.
3. Se houver pelo menos um canal confirmado, abra o gravador em **Ao vivo**. Se a imagem ainda não surgir, registre a mensagem exibida no tile ou no diagnóstico do Live View. Se houver zero confirmados, o botão Abrir todos informa que o mosaico não tem streams verificados.
4. Se o resultado for RTSP 401, teste com a **mesma conta desse NVD** no acesso Web local e confirme que ela pode ver uma câmera ativa; confira também a porta RTSP e as permissões de vídeo. Compare com o NVR que já mostrou imagens no mesmo computador. Se a coluna Evidência disser que FFmpeg está ausente, execute `./install.sh --check` neste pacote no computador que fará a visualização.

Não publique senha, URL com credencial ou diagnóstico bruto do FFmpeg. Uma captura da linha de Evidência, sem dados sensíveis, basta para determinar o próximo ajuste. O diagnóstico não altera a configuração do NVD.
