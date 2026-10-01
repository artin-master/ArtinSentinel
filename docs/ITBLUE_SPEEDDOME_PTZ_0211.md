# Artin Sentinel 0.2.11 — IT-Blue Speed Dome + PTZ local

## Perfil de campo X3-WE2Q

A Speed Dome IT-Blue disponível na LAN foi identificada pelo aplicativo do equipamento como `X3-WE2Q`, firmware da família `V5.02.R02.000A06CD`. A AKDB mantém IT-Blue como fabricante comercial e registra a família/plataforma separadamente. Credenciais, serial, IP e identificadores únicos do cliente não fazem parte da AKDB.

Capacidades observadas em campo: PTZ, rastreamento de movimento, detecção humana, alarme sonoro/luminoso, áudio full duplex e interface com três visões. A quantidade de visões no aplicativo do fabricante não é automaticamente convertida em três canais RTSP: o Sentinel persiste apenas streams distintos que forem realmente validados por `ffprobe`.

## Acesso local

O provider IT-Blue prioriza candidatos locais da família XM/iCSee, incluindo a forma `channel=0 / stream=0|1`, aliases `/onvif1` e `/onvif2`, e mantém fallbacks anteriores. Nenhuma URL é persistida sem validação de mídia.

O segundo perfil IT-Blue observado, `IPC_GK7202V300_LPG-G5-WQ`, permanece registrado apenas como evidência de campo/cloud. O Sentinel não inventa RTSP local para ele enquanto não houver um teste LAN.

## PTZ

A tela Ao vivo ganhou um painel PTZ/SPEED DOME para a câmera selecionada, com oito direções, Stop, Zoom +/- e velocidade. Nesta versão o comando local é exclusivamente ONVIF PTZ. Cada clique envia movimento limitado no tempo e tenta Stop em seguida; não existe movimento autônomo em background.

Quando a câmera possui PTZ físico conhecido mas o serviço ONVIF PTZ não responde, o Sentinel informa a limitação sem afetar o vídeo. Protocolos proprietários XM/iCSee e cloud não são usados nesta etapa.

## Próximas validações

- confirmar qual candidato RTSP abre Main/Sub da X3-WE2Q;
- verificar se ONVIF PTZ responde no firmware atual;
- identificar codec de áudio e método de talkback;
- verificar se as três visões podem ser expostas como streams locais distintos ou são composição/protocolo proprietário;
- validar presets, patrulha e tracking somente depois do PTZ básico.
