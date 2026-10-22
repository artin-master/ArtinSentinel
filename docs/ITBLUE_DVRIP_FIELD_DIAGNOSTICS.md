# IT-Blue multi-lentes: diagnóstico de campo DVRIP

Ciclo futuro 0.2.95; versão interna mantida em 0.2.94.
A reprodução física das lentes fixas permanece pendente de confirmação.

## Evidências e limites

- Cada tentativa de stream nativo cria sua própria DvripSession e socket.
- A rota salva determina channel e subtype; o número exibido pelo Sentinel
  não substitui o índice nativo.
- A sequência existente é login 1000, OPMonitor Claim 1413 e Start 1410.
  Main usa Main; Sub usa Extra1. Não foram adicionados comandos de configuração.
- O histórico Git conserva essa sequência desde a base inicial. Não há evidência
  de que uma mudança recente tenha compartilhado sockets entre lentes.
- A recepção anterior identificava JSON pelo conteúdo e podia descartar mídia
  iniciada por `{` ou inserir uma resposta JSON no meio de um frame fragmentado.
- O timeout de socket podia encerrar a espera antes do prazo total do keyframe.
- O byte T do keyframe contém codec no nibble inferior e bits de dimensão nos
  superiores; uma lista de valores completos não cobre todas as dimensões.
- Essas falhas foram reproduzidas automaticamente. Não comprovam sozinhas a
  causa no modelo instalado. Limite de sessões e recusa por channel continuam
  hipóteses que exigem observar a resposta da câmera.

Referências de implementação/protocolo:
- https://github.com/AlexxIT/go2rtc/blob/master/pkg/dvrip/client.go
- https://github.com/Moxnatiy/hass-xmeye/blob/main/docs/protocol.md (seções 6 e 8)
  descreve medições em outro equipamento XM, não homologação da IT-Blue.

## Teste físico

1. Abrir Canais, confirmar as três posições e preservar as rotas cadastradas.
2. Abrir somente fixa 1 em Main, selecionar o tile e ativar Diagnóstico do Live View.
3. Aguardar frame ou a conclusão das tentativas limitadas. Copiar as linhas DVRIP.
4. Repetir em Sub; fechar esse tile manualmente antes de testar fixa 2.
5. Repetir Main/Sub da fixa 2 e da PTZ. Conferir channel/subtype nas linhas.
6. Abrir PTZ + fixa 1 + fixa 2 juntas e comparar com os resultados individuais.
7. Confirmar imagens distintas, alternar Main/Sub e repetir a leitura de Canais.
8. Fechar uma fixa; verificar que as demais continuam e que a fechada não retorna.

## Como interpretar

- login/login_Ret: login OK ou falha; Ret é somente o código numérico.
- monitor_enviado/Ret: pedido Start enviado e último retorno observado.
  Pedido enviado não significa que o firmware aceitou ou entregou vídeo.
- chunks/bytes_transporte: chunks completos e bytes de seus corpos recebidos.
- pacotes/bytes: pacotes de mídia completos e seus bytes, incluindo header nativo.
- marcador/codec: marcador numérico anunciado e codec identificado.
- primeiro_frame/primeiro_frame_ms: frame realmente decodificado e tempo desde
  o início da tentativa; ausência de frame não é prova de canal inexistente.
- etapa=keyframe, resultado=timeout: ausência de keyframe dentro do limite.
- resultado=monitor_rejected: firmware recusou monitor; guardar Ret.
- resultado=payload_without_frame: recebeu pacote de vídeo, mas não decodificou frame.
- resultado=validated: entregou frame; confirmar também a identidade visual da lente.

Nenhuma linha deve conter senha, hash, SessionID completo ou payload de mídia.
Não alterar configurações, reiniciar, acionar luz ou sirene durante o teste.
Não retomar eventos; Hikvision segue pendente de validação física específica.
