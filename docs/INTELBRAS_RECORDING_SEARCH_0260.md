# Busca de gravações Intelbras — 0.2.60

Referência primária: **Intelbras HTTP API V3.35**, seção 4.10.5, "Find Media Files": `factory.create`, `findFile`, `findNextFile`, `close`, `destroy`. O manual descreve canal e horários na consulta e os campos StartTime, EndTime, Type, Length na resposta.

O Sentinel usa somente estas operações de consulta. A senha é fornecida ao handler de autenticação em memória e não entra na URL, tabela de resultados nem logs. Em HTTP, somente Digest é usado; Basic exige HTTPS. Redirecionamentos de busca são bloqueados. As respostas são limitadas e um erro de firmware/autorização é exibido em vez de resultados vazios fabricados.

## Teste no gravador

1. Escolha um canal e uma hora que tenham vídeo confirmado no acesso local do equipamento.
2. Em **Reprodução**, selecione o mesmo gravador/canal e os mesmos horários do relógio do DVR, no máximo 24 horas.
3. Compare a lista de trechos com o equipamento. Registre modelo, firmware, canal, período, contagem e eventual mensagem de erro; não envie senha.
4. A reprodução e exportação de arquivo ficarão para a etapa seguinte, depois de validar a busca em MHDX/NVD reais.

Esta versão não comprova suporte em todos os firmwares Intelbras nem em canais IP adicionados ao NVR. Nenhuma busca Hikvision é disparada nesta etapa.
