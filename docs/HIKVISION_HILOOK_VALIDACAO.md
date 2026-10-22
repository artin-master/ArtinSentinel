# Teste de campo .28 — gravações Hikvision e HiLook

Registrar fabricante, modelo, firmware, portas Web/RTSP e versão do Sentinel.
Não enviar senhas ou links contendo credenciais nos relatórios.

1. Começar com um DVR por IP local. Conferir a descoberta, tipo DVR/NVR, fabricante,
   modelo e canais encontrados. Manter HiLook como fabricante quando for a marca real.
2. Ler canais com a credencial do equipamento e abrir um canal por vez. Testar Main,
   Sub, Automático e o mosaico misto com os equipamentos Intelbras já conhecidos.
3. Conferir áudio em um canal que realmente possua captação. PTZ somente se o
   equipamento/canal tiver esse recurso e for disponibilizado pelo protocolo.
4. Pesquisar um dia com gravações. Conferir calendário, régua, saltos e reprodução
   em 1×; depois avaliar 2×/4×/8× conforme o protocolo retornar suporte.
5. Exportar um trecho curto em MP4, original/compacto e com/sem áudio. Confirmar
   duração, horário e reprodução do arquivo fora do Sentinel.
6. Conferir reconexão, fechamento/reabertura e restauração do mosaico. Anotar qual
   ação originou a falha e as mensagens do painel técnico.
7. Repetir com o segundo modelo/marca e depois com os equipamentos simultâneos.

O seletor de protocolo pode testar o provider Hikvision mantendo a identificação
visual original. O sucesso depende do modelo e firmware. Identificação genérica,
401 ou ausência de áudio/gravações precisam de análise, sem concluir automaticamente
senha incorreta ou compatibilidade completa.

Esta versão não introduz suporte à Cloud proprietária Hikvision/HiLook. O alvo
inicial é acesso local por IP e recursos já existentes, como RTSP e busca ISAPI
quando respondidos pelo equipamento. A ampliação de suporte seguirá as evidências
obtidas no teste. A homologação operacional na Mallet permanece pendente.

## Ordem prioritária nesta versão

1. DVR sem câmeras: cadastrar/manter o equipamento e executar Canais. Se a ISAPI
   autenticar sem inventário utilizável, conferir aviso informativo, sem erro de senha.
   Se houver canais anteriores, devem permanecer. Não inventar canais só para habilitar busca.
2. DVR com gravações: em Reprodução, escolher canal e um dia conhecido. Conferir
   trechos e régua, iniciar em 1× e comparar o horário exibido com o gravador.
3. Clicar em outro ponto da régua e testar pausa/retomada. Depois testar áudio e
   2×/4×/8×. A UI é compartilhada; a sessão nativa Intelbras não foi portada para Hikvision.
   O caminho desta rodada usa busca ISAPI e URI RTSP retornada pelo equipamento.
4. Exportar 1 minuto, conferir arquivo externo com/sem som, original/compacto.
5. Se falhar, copiar mensagens de pesquisa/reprodução/exportação do Painel técnico,
   junto com modelo/firmware e horário solicitado. Não enviar credenciais.
6. Confirmar marca na árvore e seis ações de Configurações na mesma linha em janela larga.
   Diminuir a janela: os controles devem quebrar, preservando acesso a todos.

Um gravador sem câmera atual ainda pode ter gravações antigas, desde que o canal
seja inventariado. Sem canal conhecido não há pesquisa automática nesta versão.
