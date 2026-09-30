# Recorder Intelligence Foundation — 0.2.4

A fase 0.2.4 prepara o Sentinel para aprender com vários DVRs/NVRs e câmeras sem amarrar o núcleo a uma única marca.

- providers continuam separados da identidade exibida ao operador;
- AKDB passa a registrar relações de compatibilidade reutilizáveis;
- JFL pode herdar probes Hikvision quando validados por modelo/firmware sem perder a marca JFL;
- canais lógicos continuam enumerados dinamicamente, sem assumir o número comercial do gravador;
- câmeras simples continuam protegidas contra enumeração ampla de DVR;
- relatórios de campo sanitizados passam a alimentar a revisão da AKDB.

A 0.2.4 não habilita escrita em equipamentos nem grava credenciais na AKDB.
