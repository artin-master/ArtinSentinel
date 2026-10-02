# Artin Sentinel 0.2.92 — Acesso Web confirmado e gestão de equipamentos

- A descoberta sonda HTTP e HTTPS separadamente e registra confirmação e histórico de falhas por endpoint. Porta TCP aberta e `web_url` legado continuam sendo apenas pistas.
- O acesso Web só fica disponível quando há confirmação HTTP. Vários serviços podem ser selecionados; HTTPS confirmado tem preferência e o endereço aberto contém apenas IP, esquema e porta, sem credenciais.
- A tela Configuração → Equipamentos separa cadastrados e descobertos, aproxima as ações da tabela correspondente e agrupa Canais e Excluir da descoberta em Mais.
- O cadastro manual mantém os valores e o diálogo aberto quando a validação falha; o contador da tabela mostra os resultados visíveis em relação ao total.
- A suíte automatizada cobre armazenamento, probe e integração Qt; as três fontes oficiais de versão são verificadas quanto à consistência.

# Artin Sentinel 0.2.91 — Configuração e descoberta

A aba Atualizações permite rolar verticalmente sem esmagar os campos. Equipamentos cadastrados continuam visíveis após a inclusão e após nova busca, com a marca * Incluído. Selecione a linha para ler Canais ou Excluir com a confirmação existente. Ver incluído seleciona o cadastro anterior. Equipamentos arquivados permanecem identificados para restauração.
