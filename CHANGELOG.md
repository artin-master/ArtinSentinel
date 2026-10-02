# Artin Sentinel 0.2.93 — PTZ, Stream Diagnostics & Channel Health

- PTZ usa capabilities e providers comprovados, evita inferências genéricas, preserva alvo, direção e velocidade originais para Stop, encerra o movimento ao trocar/fechar a seleção e descarta resultados atrasados associados a outra seleção.
- Diagnóstico Main/Sub cobre somente rotas cadastradas e informa codec/resolução de vídeo, faixas de áudio disponíveis e causas distintas de falha. Cancelamento não persiste resultados parciais.
- Saúde por canal reduz alertas repetidos, trata transições SEM SINAL/OFFLINE e sinaliza RECUPERADO na primeira confirmação saudável, preservando o histórico.
- Talkback consolida prontidão das rotas existentes DVRIP/Sofia, Intelbras HTTP postAudio e Intelbras NetSDK, com mensagens de dependências ausentes e sanitização de credenciais conhecidas.
- Validação física informada: MHDX 1004 e câmeras IP/MiboCam disponíveis foram usados, sem problemas aparentes nos fluxos verificados. Hikvision não foi validado fisicamente por indisponibilidade do equipamento; a validação específica permanece pendente.
- ONVIF genérico não habilita PTZ automaticamente; equipamentos atrás de gravadores não recebem capability de talkback por inferência. Não são anunciados protocolos ou compatibilidades novos.

# Artin Sentinel 0.2.92 — Acesso Web confirmado e gestão de equipamentos

- A descoberta sonda HTTP e HTTPS separadamente e registra confirmação e histórico de falhas por endpoint. Porta TCP aberta e `web_url` legado continuam sendo apenas pistas.
- O acesso Web só fica disponível quando há confirmação HTTP. Vários serviços podem ser selecionados; HTTPS confirmado tem preferência e o endereço aberto contém apenas IP, esquema e porta, sem credenciais.
- A tela Configuração → Equipamentos separa cadastrados e descobertos, aproxima as ações da tabela correspondente e agrupa Canais e Excluir da descoberta em Mais.
- O cadastro manual mantém os valores e o diálogo aberto quando a validação falha; o contador da tabela mostra os resultados visíveis em relação ao total.
- A suíte automatizada cobre armazenamento, probe e integração Qt; as três fontes oficiais de versão são verificadas quanto à consistência.

# Artin Sentinel 0.2.91 — Configuração e descoberta

A aba Atualizações permite rolar verticalmente sem esmagar os campos. Equipamentos cadastrados continuam visíveis após a inclusão e após nova busca, com a marca * Incluído. Selecione a linha para ler Canais ou Excluir com a confirmação existente. Ver incluído seleciona o cadastro anterior. Equipamentos arquivados permanecem identificados para restauração.
