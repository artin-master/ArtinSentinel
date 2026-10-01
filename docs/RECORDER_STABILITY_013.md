# Recorder Stability 0.1.3

## Falha observada em campo

Na primeira leitura física de canais da 0.1.2, o operador recebeu erro e a janela de progresso permaneceu sem uma saída clara, aparentando travamento.

O mesmo teste mostrou que o DVR descoberto anteriormente ainda aparecia como `camera` porque essa classificação já havia sido persistida pela 0.1.1.

## Correções

### RTSP bounded read

A rotina de `DESCRIBE` agora reconhece uma resposta completa por `Content-Length`. Respostas sem corpo encerram quando o cabeçalho termina. Isso elimina a espera artificial pelo timeout em cada canal.

### Fail fast

Antes da enumeração completa, o Sentinel valida uma pequena amostra de canais/subtypes. Credencial recusada, serviço inacessível ou template de URL incompatível são informados antes da varredura longa.

### Cancelamento

A leitura recebe um `threading.Event` e verifica cancelamento entre probes. O diálogo oferece Cancelar e possui limite global de segurança.

### Thread affinity

Resultado e erro do worker são conectados diretamente a métodos do `MainWindow`. Operações com widgets e com a conexão SQLite permanecem no fluxo principal da GUI.

### Migração conservadora de classificação

Ao abrir a 0.1.3, registros `camera` com provider/fabricante Intelbras e porta 37777 são promovidos para `xvr`, desde que não exista evidência explícita de câmera VIP/IPC.
