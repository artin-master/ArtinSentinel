# Recorder Route Recovery + Audio UX — 0.2.24

## MHDX 1004

A validação de campo da 0.2.23 confirmou cinco canais inventariados, mas introduziu regressão no Canal 4. A 0.2.24 preserva os canais analógicos 1–4 como caminho homologado e trata o Canal 5 como rota IP/proxy adicional exposta pelo próprio gravador. A câmera IP não precisa ser diretamente alcançável pela estação Sentinel.

## Áudio de escuta

Canais que já possuem faixa de áudio confirmada tentam reprodução imediatamente, sem executar ffprobe completo a cada clique. Se a abertura direta falhar, o diagnóstico Main/Sub e TCP/UDP permanece como fallback.

O volume passa a usar 75 como ganho unitário (1,0×) e 100 como 2,0× (~+6 dB). O slider aplica mudanças ao soltar para evitar reinícios repetidos durante o arraste.

## Validação física necessária

- MHDX: confirmar novamente Canais 1–4, principalmente Canal 4, e depois Canal 5 via DVR.
- Áudio: medir tempo de abertura e nível percebido em IT-Blue, Aitek e MiboCam.
- Confirmar que ganho máximo não introduz distorção/clipping perceptível.
