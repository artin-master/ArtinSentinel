# Verificação do piloto Cloud via ponte 0.2.94.2

Data: 18/10/2026. Base: `8583b5e98f7abb507d4dd4a9930b8a33c4097b2f`.

## Resultado e alcance

Os 24 testes novos passaram com SDK sintético compilado em C++, FFmpeg real e
interface Qt real em modo offscreen. Não foi necessário conectar um equipamento
ou executar bibliotecas do fabricante neste ambiente.

O teste isolado anterior exibiu a câmera real do DVR remoto no Linux e teve
confirmação visual do operador. A imagem real dentro do mosaico desta build ainda
aguarda teste no computador do operador. O SIM Next e a VM continuam necessários.

## Evidências automatizadas

Ambiente: Linux x86-64, Python 3.12.14, PySide6 6.12.0, pytest 8.4.2.
O computador do operador usa Python 3.14, que precisa de validação em campo.

Comando dos testes novos:

```sh
QT_QPA_PLATFORM=offscreen python3 -B -m pytest -p no:cacheprovider -q \
  tests/test_intelbras_cloud_bridge_pilot.py tests/test_intelbras_cloud_bridge_ui.py
```

Cobertura: login único; serial incorreto rejeitado antes do vídeo; senha ausente
dos logs e do SQLite; falha e crash do SDK isolados; cleanup travado limitado;
rotas inválidas rejeitadas; inventário estável sem confirmar canais não vistos;
compatibilidade do diretório do SDK; decodificação de mídia pelo FFmpeg; cadastro
na janela real; quadro no mosaico; cancelamento de login ao fechar o AS.

O teste de encerramento também foi executado em uma cópia temporária sem a
correção: falhou após esperar cerca de quatro segundos. Com a correção, passou.

A suíte completa passou de **774 aprovados / 31 falhas na base** para
**797 aprovados / as mesmas 31 falhas no piloto**, sem novos identificadores de
falha. Ela coletou 23 testes novos; o teste adicional de encerramento foi incluído
depois e passou junto dos outros 23. A lista completa aparece abaixo.

As 31 falhas preexistentes dependem de textos antigos de versão: 28 verificam
diretamente a versão antiga e três testes do instalador tentam substituir uma
string de versão que já não existe na base 0.2.94.1. Em dois destes últimos, o
fluxo chega à proteção de aplicativo aberto. Esses testes não foram modificados
para encobrir as falhas. A suíte completa não está verde.

`git diff --check`, sintaxe Bash do instalador, compilação Python e construção
do wheel passaram. O instalador completo não foi executado neste ambiente: ele
recusa root e o ambiente não permite trocar para um usuário sem privilégios.
O instalador normal no Fedora do operador ainda deve ser conferido.

## Revisão

Revisão independente de código não encontrou pendências críticas ou importantes
após corrigir atualização de sessões destacadas, confirmação de quadro vinculada
à rota efetiva, cancelamento durante encerramento, resolução do diretório do SDK
e bloqueio do diagnóstico HTTP para o cadastro Cloud.

## Próximo teste em campo

Instalar como usuário normal, manter o MV conectado no SIM, cadastrar seu serial
e porta local 55162 no AS e abrir o canal 1. Depois conferir o segundo canal,
reabertura, janela destacada e fechamento do aplicativo. Não há validação de
áudio, playback Cloud ou operação prolongada nesta etapa.

## Identificadores das falhas preexistentes

```text
tests/test_akdb_intelligence_0220.py::test_release_version_0220
tests/test_akdb_sync_field_learning_0243.py::test_release_0243
tests/test_audio_detached_dvrip_0229.py::test_release_0229_and_akdb_revision
tests/test_audio_polish_layout_0232.py::test_release_0232
tests/test_audio_stability_mosaic_fit_0225.py::test_release_0225_and_akdb_talkback_is_conservative
tests/test_bootstrap_dependencies_0242.py::test_version_0242
tests/test_capability_mapping_0213.py::test_release_is_0213
tests/test_channel_capabilities_talkback_0233.py::test_release_0233_and_akdb_revision
tests/test_channel_health_monitor_0226.py::test_version_and_health_columns_0226
tests/test_field_reconciliation_0218.py::test_release_version_0218
tests/test_fullscreen_close_update_talkback_0228.py::test_release_0228_and_official_artinupdates_default
tests/test_hikvision_performance_0222.py::test_installer_reports_real_0222_version
tests/test_hikvision_performance_0222.py::test_version_and_shared_akdb_revision_0222
tests/test_hybrid_multilens_talkback_0223.py::test_release_and_shared_akdb_0223
tests/test_installer_downgrade_guard_0253.py::test_check_never_runs_pip_even_when_package_is_older
tests/test_installer_downgrade_guard_0253.py::test_current_package_cannot_downgrade_future_release
tests/test_installer_downgrade_guard_0253.py::test_old_package_cannot_downgrade_installed_release
tests/test_intelbras_netsdk_audio_matrix_0240.py::test_release_version_0240
tests/test_intelbras_netsdk_literal_talk_0241.py::test_release_version_0241
tests/test_intelbras_netsdk_talkback_0239.py::test_release_version_0239
tests/test_intelbras_postaudio_diagnostics_0238.py::test_release_0238
tests/test_intelbras_postaudio_network_backoff_0237.py::test_release_0237
tests/test_live_view_ux_ptz_0216.py::test_release_version_0216
tests/test_multi_endpoint_status_0219.py::test_release_version_0219
tests/test_per_lens_ptz_hotfix_0234.py::test_release_0234
tests/test_recorder_route_audio_0224.py::test_release_0224
tests/test_shared_akdb_0215.py::test_release_is_0215
tests/test_talkback_transport_imx_profile_0235.py::test_release_0235_and_core_revision
tests/test_update_center_0227.py::test_version_0227_and_version_ordering
tests/test_workspace_audio_stream_0212.py::test_version_0212
tests/test_x3_talkback_profile_reconciliation_0231.py::test_release_version_0231
```
