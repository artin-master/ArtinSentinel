# Discovery Engine — 0.1.1

A descoberta usa múltiplas evidências em vez de tratar WS-Discovery como requisito.

Fluxo:

1. enumerar interfaces IPv4 privadas ativas;
2. limitar a análise a redes diretamente conectadas e no máximo /24 por interface;
3. consultar a tabela de vizinhos do kernel;
4. testar apenas portas comuns de CFTV com conexão TCP curta;
5. coletar assinatura HTTP limitada quando disponível;
6. testar existência de endpoint ONVIF sem autenticação;
7. executar ONVIF WS-Discovery;
8. correlacionar as evidências por IP;
9. persistir apenas candidatos com evidência relacionada a vídeo/CFTV.

A 0.1.1 não tenta senhas, não faz brute force, não altera equipamento e não acessa vídeo autenticado.
