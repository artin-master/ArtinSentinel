#!/usr/bin/env bash
# Optional per-user Cloud setup; system packages require explicit operator consent.
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "$0")" && pwd)"
AS_DATA="$HOME/.local/share/artin-sentinel"
AS_PREFIX="$AS_DATA/wine-cloud"
[[ ! -d "$AS_DATA/wine-cloud-teste" ]] || AS_PREFIX="$AS_DATA/wine-cloud-teste"
AS_PY="$AS_DATA/runtime/bin/python"
AS_CHECK=0
AS_YES=0
AS_NO_SYSTEM=0
for AS_ARG in "$@"; do
  case "$AS_ARG" in
    --check) AS_CHECK=1;;
    --yes) AS_YES=1;;
    --no-system) AS_NO_SYSTEM=1;;
    *) echo "Uso: bash preparar-cloud.sh [--check] [--yes] [--no-system]"; exit 2;;
  esac
done
if [[ "$EUID" -eq 0 ]]; then echo "Execute sem sudo; só a instalação de pacotes usará sudo."; exit 2; fi
have() { command -v "$1" >/dev/null 2>&1; }
if [[ -r /etc/os-release ]]; then . /etc/os-release; fi
AS_FAMILY=" ${ID:-unknown} ${ID_LIKE:-} "
case "$AS_FAMILY" in
  *fedora*|*rhel*) AS_PM=dnf; AS_PACKAGES=(wine wine-mono mingw64-win-iconv);;
  *arch*|*manjaro*) AS_PM=pacman; AS_PACKAGES=(wine wine-mono);;
  *ubuntu*|*debian*|*linuxmint*) AS_PM=apt-get; AS_PACKAGES=(wine);;
  *) echo "Distribuição sem preparação Cloud automática: ${ID:-unknown}. Instale Wine/Mono manualmente."; exit 2;;
esac
echo "Intelbras Cloud Wine • ${PRETTY_NAME:-Linux} • prefixo $AS_PREFIX"
if [[ "$(uname -m)" != x86_64 ]]; then echo "Esta ponte exige Linux x86-64."; exit 2; fi
if [[ "$AS_CHECK" -eq 1 ]]; then
  if have wine; then wine --version; else echo "Wine ausente."; fi
  [[ -f "$AS_PREFIX/drive_c/windows/Microsoft.NET/Framework64/v4.0.30319/csc.exe" ]] && echo "Arquivo do compilador presente (execução não testada)." || echo "Prefixo/Mono ainda não preparado."
  exit 0
fi
if [[ "$AS_NO_SYSTEM" -eq 0 ]]; then
  AS_ANSWER=n
  if [[ "$AS_YES" -eq 1 ]]; then AS_ANSWER=s
  elif [[ -t 0 ]]; then read -r -p "Verificar/instalar pacotes Cloud (${AS_PACKAGES[*]}) usando sudo? [s/N] " AS_ANSWER; fi
  if [[ "${AS_ANSWER,,}" == s || "${AS_ANSWER,,}" == sim ]]; then
    case "$AS_PM" in
      apt-get) sudo apt-get update; sudo apt-get install -y "${AS_PACKAGES[@]}";;
      dnf) sudo dnf install -y "${AS_PACKAGES[@]}";;
      pacman) sudo pacman -S --needed --noconfirm "${AS_PACKAGES[@]}";;
    esac
  fi
fi
have wine && have winepath || { echo "Wine/winepath ausentes. A instalação principal do AS pode ser usada sem Cloud."; exit 3; }
export WINEPREFIX="$AS_PREFIX"
if [[ -f /usr/x86_64-w64-mingw32/sys-root/mingw/bin/iconv.dll ]]; then
  export WINEPATH="Z:\\usr\\x86_64-w64-mingw32\\sys-root\\mingw\\bin${WINEPATH:+;$WINEPATH}"
fi
# All following commands run as the ordinary user, in this dedicated prefix.
timeout 90s env WINEARCH=win64 wineboot --init
AS_CSC='C:\windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe'
if ! timeout 30s wine "$AS_CSC" /help >/dev/null 2>&1; then
  AS_WINE_VERSION="$(wine --version)"
  if [[ "$AS_WINE_VERSION" == wine-9.* ]]; then
    AS_MSI="$HOME/.cache/artin-sentinel/wine-mono-8.1.0-x86.msi"
    mkdir -p "$(dirname -- "$AS_MSI")"
    if [[ ! -f "$AS_MSI" ]]; then
      echo "Baixando Wine Mono 8.1.0 do WineHQ para o Wine 9…"
      AS_TMP_MSI="$AS_MSI.part"
      if have curl; then curl --fail --location --max-time 180 https://dl.winehq.org/wine/wine-mono/8.1.0/wine-mono-8.1.0-x86.msi -o "$AS_TMP_MSI"
      elif have wget; then wget -T 30 -O "$AS_TMP_MSI" https://dl.winehq.org/wine/wine-mono/8.1.0/wine-mono-8.1.0-x86.msi
      else echo "Instale curl ou wget para baixar Wine Mono."; exit 3; fi
      mv -- "$AS_TMP_MSI" "$AS_MSI"
    fi
    printf '%s  %s\n' 0ed3ec533aef79b2f312155931cf7b1080009ac0c5b4c2bcfeb678ac948e0810 "$AS_MSI" | sha256sum --check --status || { echo "Wine Mono: checksum divergente; pacote não executado."; exit 3; }
    timeout 120s wine msiexec /i "$AS_MSI" /qn /norestart
  else
    echo "O compilador Wine Mono não executou. Confira o pacote wine-mono desta distribuição."; exit 3
  fi
fi
timeout 30s wine "$AS_CSC" /help >/dev/null 2>&1 || { echo "Wine Mono ainda não está operacional."; exit 3; }
[[ -x "$AS_PY" ]] || { echo "Instale primeiro o Sentinel com bash install.sh."; exit 3; }
AS_CLOUD_ZIP="$ROOT/vendor/intelbras-cloud-libraries.zip"
if [[ -f "$AS_CLOUD_ZIP" ]]; then
  "$AS_PY" - "$AS_CLOUD_ZIP" <<'PY'
import sys
from artin_sentinel.intelbras_wine import wine_manager
wine_manager().prepare(sys.argv[1],progress=print)
print('Ponte preparada. Nenhuma conexão com DVR foi iniciada.')
PY
else
  echo "Wine/Mono prontos. Importe SIMNextWINInstall.zip no cadastro Cloud do AS."
fi
