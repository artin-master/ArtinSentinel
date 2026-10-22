# Testes de campo — Artin Sentinel 0.2.94.30

## Instalação

1. Fechar Sentinel e probes/players de teste.
2. Extrair em uma pasta nova e executar `bash install.sh`.
3. Confirmar versão 0.2.94.30 no título. Manter cadastro e senha existentes.

## Topway da Mallet

Referência: Topway DEFENDER 16-720T3, firmware V3.4.88 build 200102.
Marca permanece Topway. Se o cadastro contém apenas Defender 16, pode editar o
modelo para DEFENDER 16-720T3 ou selecionar protocolo Hikvision explicitamente.
Porta RTSP 554. Porta proprietária 8005 não substitui RTSP. Não reiniciar DVR.

1. Ler canais novamente. IDs reais 17 (VIPC Intelbras) e 18 devem aparecer,
   mesmo com limite manual 16. Não excluir/recriar o equipamento.
2. Entradas 1–16 NO VIDEO podem continuar no inventário, mas Abrir todos não
   deve lançar streams para essas entradas se não há canais validados.
3. Abrir apenas canal 18 Main. Conferir imagem por 2 minutos, depois Sub.
4. Canal 17 Main/Sub, depois abrir as duas juntas em mosaico 4.
5. Fechar/reabrir uma câmera; o aplicativo deve permanecer responsivo.
6. Conferir diagnóstico: sem falso Watchdog 15s no primeiro segundo e sem
   I/O operation on closed file/descritor inválido ao parar/reconectar.
7. Ativar áudio no canal 18 e conferir som sem interromper vídeo. Não está
   homologado só porque o codec G.711 foi anunciado.
8. Confirmar agenda/HD em gravação no DVR. Em Reprodução, escolher o canal IP
   17 ou 18 e hoje; conferir trechos, tocar em 1x, saltar na régua e testar 4x/8x.
9. Exportar 1 minuto, abrir o MP4 fora do app e conferir imagem/duração/áudio.
   Pesquisa, velocidades, áudio e exportação deste modelo permanecem em teste.

Se falhar, copiar diagnóstico de UM canal com horário atual. Não abrir 16 canais
sem sinal nem repetir reinicializações. O teste externo anterior decodificou 163
quadros do canal 18, H.264 1920x1080, sem validar a interface desta nova build.

## Regressão

- DVR Intelbras: Live Main/Sub, áudio, playback e exportação.
- Hikvision já conhecido: calendário e reprodução LAN.
- Câmeras IP diretas e IT-Blue: abertura/fechamento sem afetar outros canais.
- Árvores: só marca colorida; AKDB/catálogo e transferência de equipamentos.
- Fedora, Mint e Arch: instalar/atualizar sem novos requisitos; testes físicos
  dos três sistemas continuam necessários, não simulados por teste unitário.
