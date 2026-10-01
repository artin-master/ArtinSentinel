# 0.1.5 — Dialog & Thread Safety

## Falha de campo

No Fedora 44, Python 3.14 e PySide6/Shiboken 6.11, o Sentinel 0.1.4 sofreu `SIGSEGV` durante o fluxo de credencial do gravador. O coredump mostrou a thread principal dentro de `QDialog::exec()` enquanto o binding PySide/Shiboken processava callback Qt.

Isso não indica erro da senha do DVR. É uma falha de estabilidade/lifetime no caminho GUI/thread.

## Correção arquitetural

O onboarding do gravador não usa mais event loop modal aninhado. Os diálogos de credencial, progresso e canais são abertos de forma assíncrona com `open()`.

A tarefa RTSP do gravador foi separada dos sinais Qt de worker. Ela executa em `ThreadPoolExecutor` Python e envia apenas mensagens de texto para uma `Queue`. A thread principal consulta essa fila via `QTimer` e é a única responsável por alterar widgets e SQLite.

O monitoramento periódico é pausado durante esse fluxo e retomado ao final. Workers Qt usados por outros módulos são mantidos em um conjunto até o `finished`, evitando coleta prematura de wrappers.

## Diagnóstico futuro

O aplicativo habilita `faulthandler` e mantém o arquivo:

`~/.local/share/artin-sentinel/logs/native-fault.log`

Esse arquivo não deve registrar senhas.

## Segurança

A senha do gravador continua somente em memória e não é persistida no SQLite nem no log.
