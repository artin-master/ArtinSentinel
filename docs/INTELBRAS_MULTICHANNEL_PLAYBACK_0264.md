# Busca Intelbras por canal e reprodução comparada — 0.2.64

A API Intelbras HTTP V3.35, seção 4.10.5, descreve `condition.Channel` começando em 1 e `items[i].Channel` começando em 0. O MHDX do teste retornou `Channel=0` para CAM 1. A busca usa o número do canal cadastrado para a condição e aceita na resposta somente `canal - 1`, normalizando o resultado ao canal exibido. O exemplo de resposta do manual contém `Channel=1` e pode representar outra variante de firmware; por isso essa regra deve ser confirmada nos NVDs e outros MHDX. Não misturar índices adjacentes sem evidência.

No modo de comparação, o Sentinel executa até quatro consultas independentes no mesmo gravador e período. Uma falha por canal é informada sem descartar as demais. A faixa temporal desenha uma linha por câmera. Clicar num horário abre apenas os canais cujos arquivos cobrem aquele instante, com o mesmo horário de início solicitado em cada URL RTSP. As sessões são independentes e podem sofrer atrasos diferentes; esta etapa não alinha timestamps de apresentação quadro a quadro. O custo de decodificação aumenta com o número de câmeras. A exportação e o corte continuam disponíveis no modo de uma câmera.

O FFmpeg usa `-readrate` e filtro de timestamps `setpts` para as velocidades 0,5×, 1×, 2× e 4×. Alguns gravadores RTSP limitam a entrega à taxa normal; velocidades maiores são solicitações, não garantia de taxa efetiva. Alterar a velocidade reinicia o fluxo no horário atual estimado pelo player.

Validar no MHDX: buscar CAM 1–4 separadamente, comparar uma hora com gravação em duas ou mais câmeras, clicar numa lacuna da faixa, trocar velocidade, conferir o relógio sobreposto das imagens e verificar CPU/rede. Se um canal retorna vazio, registrar modelo, firmware, canal e horário sem senha.
