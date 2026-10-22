# Validação 0.2.94.30 — 21/10/2026

## Escopo e evidência de campo anterior

Correção de inventário IP, roteamento por modelo exato e ciclo de processo do
Live View. Base oficial .29: SHA256 c877d29245a832496aefa167635d0c09c68281469cac09f9bc4f1125dde6788c.
O usuário confirmou IDs 17/18 por InputProxy/channels e decodificação externa de
163 quadros no canal 18 após reiniciar o Topway. Não houve acesso deste ambiente
à rede da Mallet; esse resultado não valida fisicamente a nova build.

## Verificação focada final

114 testes passaram em 2.54s. Inclui os 10 novos casos e regressões de ciclo de
vida, montagem progressiva de quadros, Hikvision, inventários, gravações ISAPI,
RTSP, AKDB, cores/cadastro, transferência, versão e instalador Cloud.
Os testes novos foram observados falhando antes das correções de inventário,
EOF/watchdog, ordem de fechamento, abertura de NO VIDEO e modelo Topway.
7 testes de reprodução persistente passaram em processo separado (10.07s).
Compilação Python, sintaxe shell e igualdade de todos os módulos Python entre
fonte e wheel verificadas. O ZIP final tem manifesto SHA256 e verificação CRC.

## Execução ampla, sem aprovação global

A execução ampla intermediária terminou com 1028 passed e 18 failed em 242.34s.
Após ajustes finais do marcador de timeout, a rodada focada foi repetida e passou.
Foi usado bloqueio de sockets externos no processo de teste; não houve consulta
intencional a equipamento físico. Testes locais usam mídia e SDK sintéticos.
A suíte ampla NÃO está toda verde. Casos que falharam:

- `tests/test_device_intelligence_0214.py::test_hikvision_rtsp_failure_reports_when_isapi_validated_password`
- `tests/test_manual_device_validation_qt.py::test_invalid_manual_address_preserves_dialog_then_saves_once[1-rtsp://host]`
- `tests/test_manual_device_validation_qt.py::test_invalid_manual_address_preserves_dialog_then_saves_once[2-rtsp://dvr.loja.interno/live]`
- `tests/test_manual_device_validation_qt.py::test_invalid_manual_address_preserves_dialog_then_saves_once[3-http://dvr.loja.interno/live]`
- `tests/test_manual_device_validation_qt.py::test_cancel_manual_dialog_never_writes[False]`
- `tests/test_manual_device_validation_qt.py::test_cancel_manual_dialog_never_writes[True]`
- `tests/test_playback_acceleration_029421.py::test_cloud_speed_command_reaches_native_sdk_without_live_network`
- `tests/test_playback_acceleration_029421.py::test_native_acceleration_advances_picture_while_bounding_output_fps`
- `tests/test_playback_acceleration_029421.py::test_rejected_cloud_acceleration_stops_after_one_login`
- `tests/test_playback_compact_02949.py::test_configuration_actions_share_one_row`
- `tests/test_playback_small_packets_029410.py::test_playback_small_packets_continue_beyond_initial_seconds`
- `tests/test_recording_history_02946.py::test_burst_sdk_playback_is_paced_at_one_x`
- `tests/test_recording_hotfix_02945.py::test_local_sdk_receives_real_speed_enum[0.5--1]`
- `tests/test_recording_hotfix_02945.py::test_local_sdk_receives_real_speed_enum[2-1]`
- `tests/test_recording_hotfix_02945.py::test_local_sdk_receives_real_speed_enum[4-2]`
- `tests/test_recording_hotfix_02945.py::test_local_sdk_receives_real_speed_enum[8-3]`
- `tests/test_recording_hotfix_02945.py::test_local_sdk_receives_real_speed_enum[16-4]`
- `tests/test_shared_playback_02948.py::test_recording_video_continues_when_audio_starts_and_stops`


A comparação desses mesmos casos na base .29 original está registrada abaixo.
Resultados agrupados de mídia não devem ser extrapolados a desempenho físico.
Falhas fora do escopo não foram escondidas alterando asserções para fazê-las passar.
A validação histórica .29 foi preservada em VALIDACAO_0.2.94.29.md.

## Limites

- Modelo Topway exato tem referência de compatibilidade de protocolo, não uma
  promoção global de homologação AKDB. Outros Topway continuam exigindo evidência.
- Áudio, agenda, playback 4x/8x e exportação Topway precisam de teste físico.
- Não foi feita atualização de firmware nem ajuste remoto de segurança/portas.
- Não adiciona exportação/importação do pacote unificado AKDB: permanece pendente.
- Não modifica ANL/ARN nem promete integração já operacional entre esses apps.
- Instalador mantém os caminhos Fedora/Mint/Arch; este ambiente não substitui
  validação física em cada distribuição.

## Comparação controlada com a base .29

Os mesmos 18 casos foram executados em processos novos na base oficial .29 e
na .30 final, com o mesmo ambiente/bloqueio externo: ambas tiveram 7 failed e
11 passed. As sete falhas foram exatamente as mesmas, sem falha nova nesse
conjunto comparativo. São testes antigos de contrato de inventário sem canais,
estrutura do diálogo de cadastro e layout de ações que já divergiam da base.
As onze falhas adicionais da execução ampla não se repetiram nesse conjunto
reduzido em nenhuma das versões; há dependência de contexto/ordem de execução,
cuja causa não foi resolvida nesta entrega. Não se declara suíte ampla limpa.

Falhas reproduzidas nas duas versões:
- `tests/test_device_intelligence_0214.py::test_hikvision_rtsp_failure_reports_when_isapi_validated_password`
- `tests/test_manual_device_validation_qt.py::test_cancel_manual_dialog_never_writes[False]`
- `tests/test_manual_device_validation_qt.py::test_cancel_manual_dialog_never_writes[True]`
- `tests/test_manual_device_validation_qt.py::test_invalid_manual_address_preserves_dialog_then_saves_once[1-rtsp://host]`
- `tests/test_manual_device_validation_qt.py::test_invalid_manual_address_preserves_dialog_then_saves_once[2-rtsp://dvr.loja.interno/live]`
- `tests/test_manual_device_validation_qt.py::test_invalid_manual_address_preserves_dialog_then_saves_once[3-http://dvr.loja.interno/live]`
- `tests/test_playback_compact_02949.py::test_configuration_actions_share_one_row`
