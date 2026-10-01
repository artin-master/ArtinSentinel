# Testes automatizados

Execute na raiz do projeto com Python 3.12 ou superior, em um ambiente
separado do runtime de produção:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install '.[test]'
test_data=$(mktemp -d)
PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
QT_QPA_PLATFORM=offscreen XDG_DATA_HOME="$test_data/data" \
XDG_CONFIG_HOME="$test_data/config" XDG_CACHE_HOME="$test_data/cache" \
ARTIN_AKDB_PATH="$test_data/akdb.sqlite3" \
.venv/bin/python -B -m pytest -p no:cacheprovider -ra
```

O extra `test` fixa a versão do pytest. As dependências de runtime mantêm
os limites existentes; este procedimento não constitui um lock completo
de todas as dependências. `python -m pytest` usa o mesmo interpretador do
ambiente e inclui a raiz do projeto no caminho de importação.

Os dados temporários isolam a execução dos dados locais do Sentinel e da
AKDB. Plugins externos, bytecode e cache do pytest ficam desativados.
Um teste de atualização usa um servidor HTTP em loopback; o ambiente
precisa permitir abrir sockets locais. Testes automatizados não substituem
validação de vídeo, áudio e PTZ com equipamentos físicos.
