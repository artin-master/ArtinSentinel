# Artin Sentinel 0.2.0 — VMS Reference Analysis

## Objetivo

Consolidar princípios operacionais observados em softwares de CFTV conhecidos sem copiar identidade visual, código ou fluxos proprietários. O objetivo é definir uma diretiva própria do Artin Sentinel para os testes de imagem, Live View, reprodução, eventos e manutenção.

## 1. Intelbras S.I.M Plus — legado operacional útil

Pontos que continuam relevantes como referência conceitual:

- operação multiequipamento e multicâmera;
- gravação local/PC-NVR como capacidade separada do gravador;
- organização por dispositivos/canais;
- alarmes e relatórios de eventos;
- mapas e operação em múltiplos monitores nas versões históricas;
- foco de estação de monitoramento, não apenas de configuração.

Diretriz Sentinel: preservar a ideia de uma estação operacional contínua, mas separar claramente vídeo, saúde e manutenção técnica.

## 2. Intelbras S.I.M Next — referência principal de fluxo desktop

Características documentadas/observadas que influenciam nossa diretiva:

- cadastro e gerenciamento de dispositivos;
- monitoramento por Intelbras Cloud;
- visualizações favoritas e planos;
- integração com conta Intelbras;
- suporte a linhas profissionais e recursos de IA quando o dispositivo suporta;
- fluxo voltado a pequenos e médios projetos de CFTV.

Diretriz Sentinel: Live View deve ser a tela principal; Sites, equipamentos e descoberta ficam em Configuração/Manutenção. Layouts precisam ser persistentes e recuperados automaticamente.

## 3. Hikvision iVMS-4200 / HikCentral — referência de ergonomia VMS

Pontos particularmente úteis:

- seleção explícita de Main/Substream pelo menu de contexto;
- Auto-Change Stream: troca de perfil conforme quantidade/tamanho das janelas;
- status da câmera e do stream próximo do Live View;
- grupos/visualizações e divisões de janela;
- reprodução, eventos e alarmes como módulos de primeira classe;
- eventos podem abrir Live View, playback e imagens relacionadas;
- gravação pode suportar main e substream quando o dispositivo oferece.

Diretriz Sentinel: o operador sempre deve saber qual stream está ativo, poder alterá-lo pelo botão direito e ter fallback Automático transparente e diagnosticável.

## 4. Positivo Casa Inteligente — referência de simplicidade

A Positivo é uma referência diferente: app móvel orientado ao usuário final. Os conceitos úteis são:

- pareamento/cadastro simples;
- Live View direto, sem expor detalhes técnicos por padrão;
- gravação local em microSD e gravação em nuvem em modelos compatíveis;
- linha do tempo/reprodução acessível pela própria câmera;
- detecção de movimento e notificações;
- áudio bidirecional e rastreamento em modelos compatíveis.

Diretriz Sentinel: a tela operacional deve permanecer simples mesmo quando o backend é técnico. Detalhes FFmpeg/RTSP ficam recolhidos em Diagnóstico e nunca poluem o mosaico.

## 5. Síntese própria — Artin Sentinel

O Sentinel não será uma réplica de nenhum desses produtos. A diretiva combinada é:

1. **Vídeo primeiro** — abrir em Ao vivo e tratar o mosaico como centro da operação.
2. **Árvore operacional** — Site → gravador → câmera/canal.
3. **Layout persistente** — grade, posição das câmeras e stream preferido sobrevivem ao reinício.
4. **Stream controlável** — Automático, Substream e Main stream; botão direito para troca imediata.
5. **Auto inteligente** — substream preferencial em mosaico e main em janela única, com fallback automático se o perfil primário falhar.
6. **Diagnóstico oculto** — FFmpeg/RTSP, tentativas, fallback e erros sanitizados sob demanda.
7. **Identidade amigável** — “DVR Casa”, “Portão”, “Garagem”, mantendo fabricante/modelo/IP separadamente.
8. **Credenciais seguras** — keyring/cofre quando disponível; nunca SQLite/log.
9. **Eventos como evidência** — Live View, playback e eventos devem convergir para o mesmo canal/horário.
10. **Saúde além do ping** — vídeo, RTSP, gravação, HDD e disponibilidade são estados independentes.
11. **Multimarca por providers** — protocolos abertos primeiro e providers específicos como enriquecimento.
12. **Degradação honesta** — função desconhecida permanece “não validada”.

## 6. O que a 0.2.0 implementa

- persistência de workspace por Site;
- restauração automática do mosaico;
- persistência das posições dos canais;
- menu de contexto no canal e no quadro;
- escolha Automático/Substream/Main stream;
- preferência opcional “Perguntar qual stream ao abrir”;
- fallback automático Substream → Main em mosaico (ou Main → Sub em visualização única);
- painel técnico recolhível de diagnóstico;
- captura sanitizada de erros do FFmpeg;
- manutenção da credencial no cofre seguro existente.

## 7. Próximas camadas previstas

- Favoritos/Planos de visualização nomeados;
- reprodução real e timeline sincronizada;
- Event Center com vínculo evento → câmera → horário;
- PTZ e áudio somente quando suportados e autorizados;
- mapa/planta;
- health check de gravação/HDD;
- providers JFL, Haiz, Positivo e Aiktek;
- integração oficial Hik-Connect/OpenAPI quando aplicável;
- Artin Bridge para acesso remoto multimarcas.

## Referências públicas consultadas

- Intelbras — S.I.M Next: https://www.intelbras.com/pt-br/ajuda-download/faq/sistema-inteligente-de-monitoramento-sim-next
- Intelbras — S.I.M Next produto: https://www.intelbras.com/pt-br/sistema-inteligente-de-monitoramento-sim-next
- Intelbras — documentação/FAQ de gravadores e SIM/SIM Plus: https://www.intelbras.com/pt-br/ajuda-download/faq/gravador-digital-de-video-em-rede-nvd-3016-p
- Hikvision — iVMS-4200 Client User Manual: https://www.hikvision.com/content/dam/hikvision/en/support/download/vms/ivms4200-series/user-manual/iVMS-4200-Client_User-Manual.PDF
- Hikvision — HikCentral Professional Control Client User Manual: https://www.hikvision.com/content/dam/hikvision/pt-br/data-sheets/HikCentral-Professional-Control-Client_User-Manual_V2.2.0_20211120-2-2.pdf
- Positivo Casa Inteligente — câmeras e suporte: https://www.positivocasainteligente.com.br/
