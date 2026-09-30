# Recorder Onboarding 0.1.2

## Objetivo

Transformar um equipamento descoberto em um gravador cadastrado e tecnicamente analisável sem realizar escrita no aparelho.

## Fluxo

1. Descoberta local identifica o candidato.
2. O operador seleciona **Adicionar selecionado ao Site**.
3. Em Equipamentos, seleciona o gravador e usa **Ler canais do gravador**.
4. Usuário e senha são recebidos pela GUI e mantidos somente em memória na sessão.
5. O Sentinel envia `RTSP DESCRIBE` para os candidatos de canal.
6. Apenas canais com resposta RTSP válida são persistidos.
7. Nenhuma mídia é puxada nesta etapa.

## Intelbras/Dahua-style

O padrão inicial sob validação é:

`rtsp://IP:554/cam/realmonitor?channel=N&subtype=1`

O uso desse padrão é uma hipótese de provider a ser confirmada por testes físicos por modelo/firmware. Falha nesse padrão não implica incompatibilidade do equipamento.

## Segurança

- senha não é salva em SQLite;
- senha não aparece no log da aplicação;
- nenhum comando de configuração é enviado;
- somente `RTSP DESCRIBE` é utilizado na enumeração de canais;
- playback e escrita permanecem desabilitados.
