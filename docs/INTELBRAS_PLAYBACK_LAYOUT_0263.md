# Reprodução visual e corte — 0.2.63

A interface foi reorganizada na estrutura típica de clientes VMS: filtros e arquivos no painel lateral redimensionável; vídeo maior no centro; faixa temporal e controles abaixo do vídeo. A identidade visual e a implementação pertencem ao Sentinel.

Depois da busca, a faixa cobre exatamente o início e o fim solicitados e pinta cada arquivo retornado como bloco verde, recortado às bordas da pesquisa. As marcas do eixo e o texto sob o cursor mostram horários do relógio local do gravador; clicar sobre um bloco seleciona o arquivo e solicita reprodução a partir da hora clicada. Clicar fora de blocos informa que não há gravação naquele instante. A barra inferior opera dentro do arquivo selecionado e mostra a hora absoluta sob o ponteiro; o tempo de reprodução exibido continua aproximado até que o decoder exponha timestamps de apresentação.

Para cortar, reproduza ou selecione um arquivo, mova a barra à posição desejada e use **Marcar início**. Repita para **Marcar fim**. O rótulo mostra os dois horários e bloqueia exportação se o fim não vier depois do início. **Baixar MP4** passa esse intervalo exato à URL RTSP do gravador e ao limite de duração do FFmpeg. Sem marcadores, exporta o arquivo selecionado inteiro, limitado à pesquisa. Os marcadores são apagados ao trocar de arquivo ou alterar a pesquisa. O arquivo MP4 só é publicado após a conversão terminar.

Validar visualmente em Fedora com PySide6, especialmente a legibilidade em janela pequena; depois testar clique na faixa e exportação de um corte curto no MHDX. Os testes locais não substituem a entrega de frames e horários pelo hardware.
