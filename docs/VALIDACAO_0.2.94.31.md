# Validação 0.2.94.31 — 21/10/2026

## Base e escopo

Base oficial 0.2.94.30, SHA256 fbffa13b22139ac32d83879f3b1c75599afd4d40f647aa3dbc853fc31334cefd.
SDK local opcional por equipamento, Ao Vivo, pesquisa e reprodução 1x em validação.
Não houve acesso deste ambiente ao DVR. Evidências físicas anteriores do usuário:
login, Main contínuo e pesquisa de gravações no Fedora; Sub sem mídia.
A reprodução pelo SDK desta build ainda exige confirmação no aparelho real.

## Verificação da integração final

45 testes focados passaram em 11.22 s. Inclui 14 testes do backend Hik SDK,
Hikvision ISAPI/RTSP preservado, Topway, versão e reprodução contínua Intelbras.
Biblioteca C++ sintética compilada contra HCNetSDK.h fornecido pelo usuário;
sem rede real, usando IPC entre processos e FFmpeg com mídia sintética.
Foram verificados vídeo ao vivo e reprodução chegando à fila de quadros,
login/consulta/fechamento/cancelamento, erro de autenticação distinguido de dia
vazio, proteção de rotas, importação persistente XDG e diálogo Qt de configuração.
As definições completas e bibliotecas proprietárias Hikvision não são distribuídas.

## Suíte ampla e comparação com a base

Execução comparativa em processos separados, TZ=America/Sao_Paulo,
QT_QPA_PLATFORM=offscreen, pytest 8.4.2, Python 3.12, PySide6 6.12 neste ambiente.
Base .30: 1032 passaram, 18 falharam (242.48 s).
Integração .31 na execução ampla: 1042 passaram, 18 falharam (244.53 s).
O conjunto das 18 falhas é idêntico. Após os ajustes finais, a regressão passou:
1048 testes passaram, com essas mesmas 18 falhas preexistentes explicitamente
desselecionadas (137.79 s). Inclui 16 casos novos do backend SDK.
A revisão também verificou fim natural da reprodução com drenagem da fila e
respeito à preferência Main/Sub salva, inclusive na janela destacada.
Não se declara suíte integral verde. A comparação não substitui validação física.

A primeira execução ampla, anterior à comparação limpa, teve duas divergências
de versão porque metadados foram atualizados durante o processo. Essa execução
não é usada como validação de versão; a comparação posterior e o teste de versão
focado foram feitos com os arquivos consistentes em 0.2.94.31.

Falhas preexistentes observadas na comparação:

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

## Verificação gráfica e empacotamento

MainWindow foi construído em offscreen com dados temporários, diálogos iniciais
cancelados e captura de hardware desabilitada no smoke. Botão SDK presente.
Diálogo novo foi renderizado e sua opção de ativação foi salva em teste Qt.
Um smoke isolado de Qt inicialmente encerrou com falha nativa após os asserts;
o teste foi corrigido para manter QApplication vivo e destruir explicitamente
os widgets, e a seleção final passou com código de saída zero.
O ambiente offscreen não comprova renderização de câmeras reais ou desempenho.

Instalador e launcher originais mantidos; wheel único 0.2.94.31. Sintaxe shell
verificada com bash -n. Wheel instalado em destino temporário: importação dos
módulos e versão corretas; todos os módulos Python do wheel idênticos à fonte.
SHA256 do wheel: 524668c1a815be7ecea14d7794ae0d0d0885a413afb920b8c1457c3959914c0d.
ZIP conferido por extração e verificação integral do manifesto SHA256SUMS.
O SDK oficial é importado pelo app e não acompanha o novo instalador.
