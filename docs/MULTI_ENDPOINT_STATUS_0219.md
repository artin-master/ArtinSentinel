# Artin Sentinel 0.2.19 — Multi-Endpoint Identity + Live Status Tree

## Objetivo

Dissociar a identidade física do equipamento do endereço IP. Um equipamento pode expor mais de um endpoint de rede sem representar mais de um dispositivo físico.

## Regra de correlação automática

A 0.2.19 só consolida automaticamente quando há evidência forte e local: **mesmo Site + mesmo MAC não vazio**. IP isolado, fabricante semelhante ou modelo semelhante não são suficientes para merge automático.

## Persistência

- `devices`: mantém a identidade física canônica e também preserva linhas históricas anteriores.
- `devices.correlated_to`: aponta uma linha histórica secundária para a identidade física canônica.
- `device_endpoints`: armazena os endereços e rotas Web/RTSP/ONVIF de cada endpoint.

Nenhuma linha histórica é apagada durante a correlação.

## Monitoramento

Todos os endpoints conhecidos são diagnosticados em paralelo. O estado físico é Online quando pelo menos um endpoint responde. O estado individual de cada endpoint permanece disponível para diagnóstico.

## Interface

A árvore do Live View apresenta um único equipamento físico e indicadores de status. A tela Equipamentos mostra o IP principal e a quantidade de endpoints adicionais, com os detalhes completos no tooltip/painel contextual.

## Caso de campo IT-Blue

A X3-WE2Q/XM535D1 observada em `192.168.15.46` e `192.168.15.47`, ambos no MAC `bc:ad:ae:2a:60:bf`, é o primeiro caso físico usado para validar esta arquitetura.
