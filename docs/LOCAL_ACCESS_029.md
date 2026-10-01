# Local Access 0.2.9

## Diretriz

Acesso local/LAN é a prioridade atual do Artin Sentinel. ONVIF, RTSP e HTTP/HTTPS devem estar estáveis e validados por fabricante/modelo antes de adicionar dependências de Intelbras Cloud, Hik-Connect, P2P proprietário ou Artin Bridge.

## Aitek SIGMA-SEG6050BP

Dados de campo fornecidos pelo próprio equipamento:

- fabricante comercial: Aitek;
- modelo comercial: SIGMA-SEG6050BP;
- plataforma/modelo interno observado: H2-52PGX;
- câmera IP PoE, 1 canal real;
- RTSP: porta 554;
- Main: `/live/0/MAIN`;
- Sub: `/live/0/SUB`;
- Main observado: H.265+, 2880x1620;
- Sub observado: H.265+, 800x448;
- áudio observado: G.711u.

O Sentinel tenta primeiro os caminhos RTSP acima e somente persiste o canal após confirmação de vídeo por ffprobe/libavformat.

A plataforma H2-52PGX é tratada como pista de compatibilidade. Ela não é, sozinha, prova de que qualquer outro equipamento OEM seja Aitek.

## Interface Web

Quando a descoberta confirmar HTTP/HTTPS, o equipamento pode ser aberto no navegador padrão por **Web / Abrir interface Web**. O Sentinel não adiciona usuário ou senha na URL e não inventa portas não detectadas.
