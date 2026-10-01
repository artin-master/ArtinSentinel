# Enumeração híbrida de canais — 0.2.2

O Sentinel não deve inferir quantidade de canais pela nomenclatura comercial do gravador.

Exemplos de campo:

- MHDX 1004 pode possuir 4 entradas analógicas + canal IP adicional;
- NVRs comerciais de 16 canais podem expor mais canais lógicos conforme família/firmware.

A enumeração diferencia:

1. capacidade nominal;
2. entradas físicas;
3. canais lógicos expostos;
4. canais efetivamente com stream.

Câmeras IP simples não passam pela varredura ampla de gravador sem evidência explícita de que são equipamentos multicanal.
