# Gravações: primeira etapa 0.2.58

## Já disponível

Em Reprodução, selecionar um gravador cadastrado com URL Web validada e abrir a interface do equipamento no navegador. O acesso segue as credenciais e permissões do próprio gravador. A lista de gravadores usa o Site ativo e seus canais já cadastrados. A interface do Sentinel não promete resultados de gravação nem solicita ou armazena uma segunda senha.

## Próxima validação em aparelho

1. Selecionar um gravador Intelbras com imagens antigas conhecidas; anotar modelo, canal, dia e intervalo que apareçam no próprio gravador.
2. Conferir a documentação do SDK instalada para localizar funções de pesquisa de arquivos e reprodução remota para este firmware. Criar probe somente leitura que retorna início, fim, canal e tipo sem salvar a mídia.
3. Comparar o probe com as gravações vistas no gravador. Falha de permissão, disco ausente, relógio fora de sincronia e lista vazia devem ser estados separados.
4. Só após respostas reais confirmadas, conectar busca por data e canal à interface e acrescentar reprodução e exportação sob demanda.
5. Repetir o processo de validação do provider Hikvision em outra etapa.

Os testes automáticos desta versão não demonstram reprodução de arquivo gravado. A consulta Web é o único acesso funcional a gravações entregue nesta etapa.
