# Large Site Scaling Foundation — 0.2.3

## Contexto

Sites como a Mallet possuem mais de 100 câmeras/canais. A interface não pode limitar o operador a 16 janelas.

## Grades disponibilizadas

1, 4, 9, 16, 25, 36, 49, 64, 81, 100 e 144.

## Adaptação inicial

A 0.2.3 reduz a densidade visual dos tiles e o FPS alvo de saída conforme a grade cresce. Isso é uma medida inicial, não uma promessa de 144 streams decodificados simultaneamente em qualquer computador.

## Próxima arquitetura de escala

- aceleração de decode por GPU/VA-API/NVDEC/QSV quando disponível;
- substream obrigatório/preferencial em mosaicos grandes;
- suspensão ou redução dinâmica de FPS para tiles minúsculos/invisíveis;
- múltiplos workspaces/páginas por Site;
- múltiplos monitores;
- orçamento de CPU/GPU/rede e adaptação automática;
- separar canais cadastrados/monitorados de streams efetivamente decodificados.
