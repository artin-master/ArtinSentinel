# Ciclo futuro 0.2.95 — eventos locais IT-Blue

Base oficial: Artin Sentinel 0.2.94, commit
`216f52825dad16c04517c6379e8ba7d023f0a003`.
A versão interna permanece **0.2.94** durante o desenvolvimento.
Não foi preparada release, build, tag, publicação ou push neste bloco.
O fechamento futuro segue [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md).

## Implementação

- Sonda explícita no Live View → menu ⋮ do inspector →
  **Sonda de eventos IT-Blue (somente leitura)**. Nenhuma conexão de eventos
  inicia automaticamente ao abrir vídeo, selecionar equipamento ou iniciar o app.
- Sessão DVRIP/Sofia dedicada, com um único leitor. Não reutiliza sockets de
  vídeo, PTZ ou talkback. A sessão existe até desligar a sonda, trocar Site,
  mudar/remover o endpoint ou encerrar o aplicativo.
- Dialeto OpenIPC/python-dvr: login `1000`, assinatura `GUARD_REQ/AlarmSet 1500`
  com `Name` vazio, notificações `AlarmInfo 1504`, keepalive `1006` e consultas
  `ConfigGet 1042`. IDs e payloads ficam no provider, não na UI.
  Não tenta IDs alternativos cegamente. Uma resposta de sucesso à assinatura
  não comprova que Motion/Human estejam disponíveis neste firmware.
- Backoff 1, 2, 4, 8… até 60 segundos; volta a 1 após sessão estável por
  60 segundos. Rejeição de credenciais/assinatura ou dialeto não suportado
  exige intervenção do operador, sem repetição automática.
- Framing suporta fragmentação e timeouts sem perder bytes. Pacote limitado
  a 64 KiB, eventos intercalados limitados a 64 e fila normalizada a 128.
  Fila cheia descarta notificações e incrementa contador do diagnóstico.
- Shutdown cancela o worker, fecha o socket e aguarda sua thread com orçamento
  compartilhado de quatro segundos. Eventos posteriores ao cancelamento não
  chegam à UI nem ao banco.

## Eventos, estado e canais

Normalização conservadora:

| Nome informado | Estado explícito | Tipo |
| --- | --- | --- |
| VideoMotion / MotionDetect | Start / Stop | motion_start / motion_stop |
| HumanDetection / HumanDetect / PersonDetect | Start / Stop | human_start / human_stop |
| Outro evento ou estado não reconhecido | Sem interpretação | alarm_unknown |

Não converte movimento em pessoa, nem infere aproximação. Payload malformado
é descartado. Só permanecem tipo permitido, índice inteiro de canal, timestamp
local e motivo controlado. Não há payload bruto, senha, hash, SessionID ou mídia
no histórico/diagnóstico.

Start repetido atualiza a validade em memória sem duplicar o histórico.
Stop repetido/órfão não grava. Replay de um incidente recém-encerrado é suprimido
por dois segundos; eventos desconhecidos têm janela de cinco segundos.
Sem Stop, o indicador expira após 30 segundos sem renovar Start. O histórico
marca `safety_timeout`, sem afirmar que a câmera reportou Stop. Desligar a sonda
marca `subscription_stopped`. Índices nativos diferentes permanecem independentes,
mesmo quando só é possível indicar o evento no equipamento.

**Índice de alarme não é automaticamente índice de lente.** Rotas cadastradas
fornecem candidatos, mas somente uma correlação física registrada para o mesmo
endpoint/firmware permite badge no tile. Sem isso, a indicação fica no inspector:
`Equipamento: Movimento/Pessoa (canal não correlacionado)`. O diagnóstico mostra
separadamente o índice nativo recebido. Não há alteração do mosaico, stream,
áudio, gravação ou PTZ.

Formato de evidência de correlação no metadata do equipamento, reservado a uma
validação física documentada (não preenchido automaticamente nesta rodada):

```json
{
  "dvrip_event_channel_correlation": {
    "source": "physical_test",
    "endpoint": "IP do endpoint validado",
    "firmware": "firmware do inventário validado",
    "channels": [{"native_channel": 0, "channel_id": 123}]
  }
}
```

Os IDs são do inventário real. O par precisa corresponder a uma rota DVRIP/XM
inequívoca cadastrada; índices duplicados/ambíguos são rejeitados. Mudança de
firmware/endpoint invalida a correlação. Não usar este exemplo como confirmação.
A UI ainda não oferece assistente de homologação dessa correlação: primeiro
coletar índices e testar fisicamente, depois registrar evidência revisada.

## Histórico e diagnóstico

Reutiliza a tabela SQLite `events`, sem schema/banco novo e sem alterar PRAGMAs.
Cada transição registra Site e equipamento do inventário, canal quando comprovado,
tipo, timestamp UTC, origem `dvrip-sofia` e motivo controlado; severidade `info`.
Início/fim são linhas separadas correlacionáveis por equipamento/canal/índice/tipo.
O histórico sobrevive ao restart, mas o badge e a assinatura não são restaurados
automaticamente. Uma queda abrupta do processo pode deixar apenas o início no
histórico; não se inventa Stop retroativo.

O menu **Diagnóstico de eventos locais** abre o painel de diagnóstico existente.
Mostra suporte sim/não/desconhecido, assinatura ativa, último evento, canal
correlacionado/índice nativo, horário local UTC, último reconnect, erro fixo,
descartes por limite de fila e modelo/firmware sanitizados do inventário.
O painel e o tooltip acompanham a sonda sem modais repetitivos.

A evidência `dvrip_event_evidence` no metadata local separa assinatura aceita dos
tipos recebidos via LAN, com fonte `local_protocol_observation`, confiança
`protocol_response_only`, validação física pendente e `homologated: false`.
Não modifica/publica perfis compartilhados da AKDB nem transforma observação
no app móvel em capability local homologada.

## Alarme/dissuasão: somente leitura

Consultas permitidas: `Detect`, `Detect.MotionDetect`, `Detect.HumanDetection`,
`Detect.HumanDetect`. Um firmware pode recusar alguns nomes sem fornecer evidência.
O resumo aceita somente booleans `Enable`, `BeepEnable`, `FlashEnable`,
`AlarmOutEnable`, `RecordEnable`, `MsgtoNetEnable` e `Level` inteiro limitado.
Agenda e campos desconhecidos são descartados por falta de schema suficiente.

| Função | Evidência atual | Limite |
| --- | --- | --- |
| Motion / Human / Start / Stop | Família/protocolo; parser automatizado | Não confirmado fisicamente na IT-Blue nesta rodada |
| BeepEnable / FlashEnable / AlarmOutEnable | Campos de configuração, se retornados | Linkage configurado, não estado físico instantâneo |
| Luz/sirene/alerta por aproximação no app | Observação de campo fornecida pelo usuário | Não comprova comando/evento equivalente via LAN |
| WhiteLight / FloodLight / WarningLight / Siren / Buzzer / Deterrence / IVS | Nomes/funções da família, schema local ainda não verificado | Nenhuma integração ativa ou novo comando |
| Sensibilidade | Level, somente se retornado como inteiro permitido | Sem alteração |
| Agenda / automação completa | Schema ainda pendente | Sem alteração nem interpretação livre |

Não envia `ConfigSet`, `OPNetAlarm`, reboot, sirene, luz, sensibilidade ou agenda.
Nenhuma câmera foi acessada nesta etapa de desenvolvimento. A própria câmera
pode acionar sua automação existente durante movimento; o teste físico precisa
distinguir essa automação de qualquer efeito inesperado de assinatura no firmware.

Referências consultadas (evidência da família, não homologação do modelo):
[OpenIPC/python-dvr, assinatura e leitura Detect](https://github.com/OpenIPC/python-dvr/blob/master/dvrip.py),
[exemplos/capabilities da família](https://github.com/OpenIPC/python-dvr).

## Teste físico IT-Blue

1. Abrir a IT-Blue cadastrada no Live View, com credencial LAN e IP do endpoint.
2. Selecionar o tile e ativar **⋮ → Sonda de eventos IT-Blue (somente leitura)**.
3. Abrir **Diagnóstico de eventos locais**; verificar assinatura ativa. Se houver
   recusa, registrar código, modelo/firmware e encerrar a sonda, sem mudar a câmera.
4. Passar diante da câmera. Anotar tipo Motion/Human, índice nativo e horário
   apresentados; não considerar movimento como prova de detecção humana.
5. Confirmar Start. Sem correlação física registrada, conferir indicação no
   equipamento; com correlação validada, conferir badge exclusivamente no tile certo.
6. Sair da área; esperar Stop. Se não chegar, conferir expiração em 30 segundos
   sem Start e motivo `safety_timeout` no histórico.
7. Conferir **Eventos**: início/fim, Site, equipamento, índice e canal quando
   comprovado. Repetir Start, desconectar/reconectar LAN e verificar ausência
   de duplicações e backoff, com vídeo/áudio dos outros canais preservados.
8. Repetir separadamente em outra lente/canal quando aplicável. Não registrar
   correlação antes de provar qual lente produz qual índice de evento.
9. Desativar a sonda; trocar Site; fechar o aplicativo durante espera/reconnect.
   Confirmar que a sessão encerra e não volta sozinha.
10. Confirmar que o Sentinel não enviou acionamento de luz/sirene. Comparar com
    automações já configuradas na câmera antes da sonda, sem alterar essas regras.

Registrar por firmware/modelo: **confirmado**, **parcialmente confirmado**,
**não suportado neste dialeto** ou **inconclusivo**. Assinatura aceita sem
notificação é inconclusiva; não comprova ausência de detecção no equipamento.
Ainda falta validação física da assinatura, dos nomes de eventos, Start/Stop,
keepalive prolongado e da correlação entre lentes/índices. Hikvision continua
pendente de teste físico específico por indisponibilidade de hardware; seu
suporte existente não foi alterado.

## Validação automatizada

Testes focados em `test_dvrip_events.py`, `test_camera_events.py` e
`test_camera_event_ui_qt.py`, incluindo regressões existentes de Live View,
áudio e shutdown. Testes simulam protocolo/firmware; não substituem campo.
Resultado final: **79 testes focados aprovados** e **729 coletados/aprovados**
na suíte completa (0 falhas, 0 erros, 0 skipped), em 79,63 segundos. São 47
testes novos; os 682 da base continuam aprovados. `git diff --check` passou.
A suíte completa foi executada uma vez após os testes focados, com autorização
para servidores HTTP/TLS de teste em loopback. Nenhum equipamento real foi
acessado e nenhum teste físico deste recurso foi declarado confirmado.
