# Validação 0.2.94.32 — 22/10/2026

Base: instalador completo oficial 0.2.94.31. Escopo e roteiro em TESTES_0.2.94.32.md.
Não houve acesso ao DVR ou à rede do usuário. Testes usam Linux x86_64, Python 3.12,
PySide6 6.12, pytest 9.1.1, FFmpeg local, TZ America/Sao_Paulo e Qt offscreen.

## Resultado

- Regressão geral: 1065 passaram, 12 falhas preexistentes explicitamente desselecionadas, 141.72 s.
- Após os últimos ajustes no validador: 33 testes de mídia/exportação passaram em 13.15 s.
- Confirmação final da política de acesso e demais novos testes unitários: 9 passaram em 0.70 s.
- IPC real entre processos, SDK sintético compilado contra HCNetSDK.h fornecido pelo usuário,
  vídeo e áudio sintéticos, FFmpeg/FFprobe reais. Exportação Original/Compacto, com e sem áudio,
  gera arquivo reproduzível; validação rejeita vídeo curto mesmo com áudio longo e erro nativo posterior.
- Comandos de aceleração normal/rápido/lento conferidos contra o cabeçalho. Aceitação simulada
  não comprova velocidade no hardware; observar taxa medida no teste de campo.
- MainWindow construído, novos controles presentes e tabela assíncrona de 8 componentes
  concluída em offscreen. Tema existente aplicado e telas inspecionadas visualmente.
- bash -n no instalador/launcher, compileall, wheel instalado em destino temporário,
  importações e versão conferidas; bytes dos módulos no wheel comparados às fontes.
- ZIP reextraído e manifesto SHA256SUMS verificado integralmente. Um único wheel .32.
- Runtime Intelbras Cloud e demais binários vendor idênticos à base .31.

A primeira execução ampla apontou 24 falhas: as 18 anteriores e 6 testes que dependiam
literalmente de rótulos antigos, quantidade de botões e um fixture de troca de velocidade.
Foram atualizados os contratos de interface aprovados pelo usuário e os fixtures.
Também foram atualizados os testes antigos do cadastro para identificar os campos por
objectName e considerar a referência AKDB já existente; cinco falhas antigas desapareceram.
O antigo teste de botões de configuração foi atualizado para Exportar/Importar equipamentos.
O fixture antigo do exportador passou a fornecer stderr e isolar somente a publicação;
a validação de mídia é coberta pelos testes reais separados. A regressão final não apresentou
novas falhas. Não se declara suíte integral verde; as 12 pendências abaixo continuam abertas.

## Falhas anteriores mantidas em separado

- `tests/test_device_intelligence_0214.py::test_hikvision_rtsp_failure_reports_when_isapi_validated_password`
- `tests/test_playback_acceleration_029421.py::test_cloud_speed_command_reaches_native_sdk_without_live_network`
- `tests/test_playback_acceleration_029421.py::test_native_acceleration_advances_picture_while_bounding_output_fps`
- `tests/test_playback_acceleration_029421.py::test_rejected_cloud_acceleration_stops_after_one_login`
- `tests/test_playback_small_packets_029410.py::test_playback_small_packets_continue_beyond_initial_seconds`
- `tests/test_recording_history_02946.py::test_burst_sdk_playback_is_paced_at_one_x`
- `tests/test_recording_hotfix_02945.py::test_local_sdk_receives_real_speed_enum[0.5--1]`
- `tests/test_recording_hotfix_02945.py::test_local_sdk_receives_real_speed_enum[2-1]`
- `tests/test_recording_hotfix_02945.py::test_local_sdk_receives_real_speed_enum[4-2]`
- `tests/test_recording_hotfix_02945.py::test_local_sdk_receives_real_speed_enum[8-3]`
- `tests/test_recording_hotfix_02945.py::test_local_sdk_receives_real_speed_enum[16-4]`
- `tests/test_shared_playback_02948.py::test_recording_video_continues_when_audio_starts_and_stops`

## Limites físicos

A reprodução relatada pelo usuário funciona, mas os registros de campo recebidos não
comprovaram que aquele teste usava o novo SDK. Esta versão mostra o backend explicitamente
e limpa os resultados ao trocar acesso. Aceleração e exportação SDK exigem validação real.
Substream desse DVR, áudio de escuta SDK Hikvision e Hik-Connect não são declarados funcionais.
A origem exata do MP4 ausente anterior não estava no log; os novos erros detalhados e
validações permitirão identificá-la se persistir. Não afirmar correção física sem esse teste.
Fedora/Mint/Arch mantêm o instalador por distribuição; não foram instalados fisicamente aqui.
