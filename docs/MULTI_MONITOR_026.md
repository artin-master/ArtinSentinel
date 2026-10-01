# Multi-Monitor Foundation — 0.2.6

## Conceito

O Sentinel passa a permitir janelas independentes de Live View. Cada janela pode ser arrastada para outro monitor e ter seu próprio mosaico, seleção e conjunto de streams.

## Persistência

Por Site, cada janela secundária salva:

- chave da janela;
- monitor atual;
- posição e tamanho;
- grade;
- canais por slot;
- preferência de stream por slot;
- estado de tela cheia.

Ao iniciar, as janelas salvas são restauradas. Se o monitor registrado não existir, a janela é reposicionada no monitor principal.

## Tela cheia

Há dois conceitos independentes:

- tela cheia do mosaico atual;
- tela cheia de uma câmera individual. Nesse caso o Sentinel tenta Main stream temporariamente e restaura o workspace anterior ao sair.

## Limitações atuais

A 0.2.6 ainda não compartilha uma única decodificação entre duas janelas que exibem a mesma câmera. Cada janela possui sua sessão independente. O compartilhamento de decode e otimizações de 100+ streams ficam para uma fase de performance posterior.
