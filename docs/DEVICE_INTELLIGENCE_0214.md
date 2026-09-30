# Artin Sentinel 0.2.14 — Device Intelligence + Field Stabilization

## Objetivo

A 0.2.14 consolida quatro problemas observados no teste físico da 0.2.13: roteamento incorreto de DVR Hikvision para o fluxo de câmera IP, áudio sem reprodução, ergonomia insuficiente do PTZ e AKDB sem tipo de equipamento como conhecimento estrutural.

## AKDB como base de conhecimento

Cada perfil pode declarar um `canonical_type`, além de fabricante, família, modelo, provider, capacidades, protocolos e evidências. A interface exibe explicitamente o **Tipo de equipamento**.

A identidade operacional segue a ordem:

1. override manual definido pelo operador;
2. perfil AKDB específico e confiável;
3. identidade persistida/detectada;
4. desconhecido quando não há evidência suficiente.

A camada manual não apaga a camada detectada. Isso permite auditar divergências e corrigir roteamento sem perder evidência de descoberta.

## Hikvision DVR/NVR

Quando o tipo operacional é DVR/NVR/XVR e o provider é Hikvision/JFL compatível, o Sentinel usa o scanner de gravador Hikvision e os padrões `/Streaming/Channels/{canal}01/02`.

A enumeração não usa mais os canais 1–4 como pré-condição. Um gravador com câmeras somente em entradas posteriores continua sendo analisado até o limite definido pela AKDB.

Antes da enumeração RTSP, uma consulta **ISAPI GET somente leitura** em `/ISAPI/System/deviceInfo` tenta confirmar autenticação e coletar identificação básica. Se ISAPI aceitar a credencial mas RTSP falhar, o diagnóstico informa essa distinção para evitar classificar automaticamente o problema como senha incorreta.

Nenhuma alteração de configuração remota é realizada por esse probe.

## Áudio

O áudio continua separado do decoder de vídeo. Para cada candidato Main/Sub:

1. `ffprobe` confirma se existe uma faixa de áudio e identifica codec/taxa/canais;
2. o Sentinel verifica se o decoder local existe;
3. tenta `ffplay/SDL`;
4. se esse backend encerrar/falhar, tenta FFmpeg em Pulse/PipeWire;
5. por fim tenta FFmpeg/ALSA quando disponível.

O diagnóstico do Live View mostra o backend efetivamente usado ou a causa sanitizada da falha.

## PTZ

O console PTZ foi reorganizado como controle único de VMS:

- D-pad maior para oito direções;
- `STOP` central destacado;
- Zoom −/+ separado;
- velocidade percentual integrada ao mesmo bloco.

A camada de comando existente permanece conservadora: movimentos são limitados e dependem da capacidade PTZ efetivamente exposta pelo equipamento/provider.

## Teste de campo

A 0.2.14 precisa de validação física antes de considerar os três problemas resolvidos. O teste prioritário deve verificar Hikvision DS-7216HGHI-F1, áudio real em câmeras/gravadores já conhecidos e a IT-Blue Speed Dome usada nos testes anteriores.
