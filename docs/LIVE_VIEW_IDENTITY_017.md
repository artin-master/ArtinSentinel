# Artin Sentinel 0.1.7 — Live View + Identity

## Objetivo

Converter os canais RTSP confirmados no MHDX 1004 em fontes de vídeo operacionais no workspace VMS e separar claramente identidade técnica de identidade operacional.

## Pipeline de Live View

```text
DVR/NVR/câmera
   ↓ RTSP somente leitura
FFmpeg (processo decoder)
   ↓ RGB24 640x360
thread Python + fila limitada
   ↓ polling ~80 ms
thread principal Qt
   ↓ QImage/QPixmap
VideoTile
```

Nenhum widget Qt é manipulado pelo thread/processo de decodificação.

## Perfis de stream

Cada canal possui `main_rtsp_url`, `sub_rtsp_url` e `preferred_stream`.

- `auto`: substream quando há mais de um quadro; main stream na visualização única;
- `sub`: força substream;
- `main`: força main stream.

A URL persistida nunca contém usuário ou senha.

## Identidade

### Equipamento

- `name`: nome operacional, por exemplo `DVR Casa`;
- `detected_name`: nome observado pela descoberta;
- `manufacturer`, `model`, `ip`: identidade técnica separada;
- `name_locked`: impede que uma redescoberta substitua o nome operacional.

### Canal

- `source_name`: nome entregue pelo provider/gravador quando existir;
- `alias`: nome manual definido pelo operador;
- nome exibido = `alias` → `source_name` → nome genérico do canal.

A arquitetura já suporta sincronizar nomes do DVR quando um provider conseguir obtê-los. No perfil MHDX atual, caso o gravador não exponha nome de canal no método usado, o fallback permanece `Canal 01`, `Canal 02` etc.

## Credenciais

- usuário e indicador de credencial salva ficam no SQLite;
- senha fica exclusivamente no keyring/cofre seguro do sistema;
- sem keyring utilizável, a senha fica apenas na memória da sessão;
- não existe fallback em texto puro;
- logs e banco não recebem senha nem URL autenticada.

## Limitações atuais

- Live View requer `ffmpeg` instalado no sistema;
- playback ainda não está implementado;
- gravação/HDD continuam como “não validados”;
- o decoder FFmpeg recebe a credencial somente em runtime para abrir o RTSP; o Sentinel não a registra em logs/SQLite;
- nomes nativos de canal dependem do que cada provider conseguir consultar de forma documentada/somente leitura.
