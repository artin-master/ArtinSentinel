# Teste de campo — Artin Sentinel 0.2.38

## iMX C

- Abrir a câmera diretamente.
- Confirmar áudio de escuta.
- Selecionar Webcam C270 e ganho +6 dB.
- Acionar MIC por 5–10 s e encerrar.
- Copiar as linhas `HTTP 1/6` até `HTTP 6/6`, `PTT envio`, `Fallback HTTP` e qualquer erro.
- Informar se houve voz no alto-falante da câmera.

## MHDX 1004

- Abrir um canal para o qual a API oficial declarou saída de áudio.
- Repetir o mesmo fluxo de MIC.
- Comparar se singlepart se mantém, se ocorre fallback multipart e se o decoder buffer é suportado.

## Resultado esperado

O Sentinel não deve mostrar “Falando” apenas após o primeiro frame local. Se não houver confirmação do decoder, deve permanecer em estado de transmissão/aguardando confirmação ou sessão estável.
