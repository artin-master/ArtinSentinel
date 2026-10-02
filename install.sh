#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
VENV="$HOME/.local/share/artin-sentinel/runtime"
BIN="$HOME/.local/bin"
APPS="$HOME/.local/share/applications"
ICONS="$HOME/.local/share/icons/hicolor/512x512/apps"
DATA="$HOME/.local/share/artin-sentinel"
NEW_VERSION="0.2.94"
PREV_VERSION=""

CHECK_ONLY=0
ASSUME_YES=0
NO_SYSTEM=0
MINIMAL=0
ALLOW_DOWNGRADE=0

usage() {
  cat <<'TXT'
Uso: ./install.sh [opções]

Opções:
  --check       Somente diagnostica dependências; não instala nem altera arquivos.
  --yes         Confirma automaticamente a instalação de pacotes do sistema.
  --no-system   Não tenta instalar pacotes do sistema.
  --minimal     Instala/verifica apenas dependências essenciais.
  --allow-downgrade  Autoriza explicitamente instalar uma versão anterior.
  -h, --help    Mostra esta ajuda.

Sem opções, o instalador detecta dependências ausentes e, em terminal interativo,
oferece instalá-las antes de instalar/atualizar o Artin Sentinel.
TXT
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --check) CHECK_ONLY=1 ;;
    --yes) ASSUME_YES=1 ;;
    --no-system) NO_SYSTEM=1 ;;
    --minimal) MINIMAL=1 ;;
    --allow-downgrade) ALLOW_DOWNGRADE=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Opção desconhecida: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

if [[ "${EUID}" -eq 0 ]]; then
  echo "Não execute o instalador como root. Ele usa sudo somente quando pacotes do sistema precisam ser instalados."
  exit 1
fi

if [[ -r /etc/os-release ]]; then
  # shellcheck disable=SC1091
  . /etc/os-release
else
  ID="unknown"
  ID_LIKE=""
  PRETTY_NAME="Linux"
fi

have() { command -v "$1" >/dev/null 2>&1; }
media_ok() { python3 "$ROOT/tools/check_media_runtime.py" --quiet; }
decoders_missing() {
  ! have ffmpeg && return 0
  local inventory
  inventory="$(ffmpeg -hide_banner -decoders 2>/dev/null || true)"
  grep -Eq '^[[:space:]]*[A-Z.]{6}[[:space:]]+h264([[:space:]]|$)' <<<"$inventory" || return 0
  grep -Eq '^[[:space:]]*[A-Z.]{6}[[:space:]]+hevc([[:space:]]|$)' <<<"$inventory" || return 0
  return 1
}

python_ok() {
  have python3 && python3 - <<'PY' >/dev/null 2>&1
import sys
raise SystemExit(0 if sys.version_info >= (3, 12) else 1)
PY
}

venv_ok() {
  have python3 && python3 -m venv --help >/dev/null 2>&1
}

installed_version() {
  if [[ -x "$VENV/bin/python" ]]; then
    "$VENV/bin/python" -c 'from importlib.metadata import version; print(version("artin-sentinel"))' 2>/dev/null || true
  fi
}

version_relation() {
  python3 - "$1" "$2" <<'PY'
import re
import sys
installed, requested = sys.argv[1:]
if not all(re.fullmatch(r"[0-9]+(?:\.[0-9]+){2,3}", v) for v in (installed, requested)):
    print("unknown")
else:
    old, new = (tuple(int(n) for n in v.split(".")) for v in (installed, requested))
    print("newer" if old > new else "older" if old < new else "same")
PY
}

# Match the actual Sentinel entrypoint, not a broad substring that could hit
# the installer itself or an unrelated process. Also cover `python -m` launches
# of this same application from a source checkout.
running_sentinel_pids() {
  python3 - "$VENV/bin/artin-sentinel" "$BIN/artin-sentinel" <<'PY'
import os
import sys
from pathlib import Path

targets = set(sys.argv[1:])
for entry in Path("/proc").iterdir():
    if not entry.name.isdecimal() or int(entry.name) == os.getpid():
        continue
    try:
        if entry.stat().st_uid != os.getuid():
            continue
        # A terminated process can briefly remain as a zombie in /proc.
        # It no longer has the application open and must not block an update.
        if (entry / "stat").read_text().split(") ", 1)[1][0] == "Z":
            continue
        argv = [os.fsdecode(item) for item in (entry / "cmdline").read_bytes().split(b"\0") if item]
    except (OSError, PermissionError, IndexError):
        continue
    if any(arg in targets for arg in argv) or any(
        argv[i:i + 2] == ["-m", "artin_sentinel.app"] for i in range(len(argv) - 1)
    ):
        print(entry.name)
PY
}

require_sentinel_closed() {
  local pids answer
  while true; do
    if ! pids="$(running_sentinel_pids)"; then
      echo "ERRO: não foi possível verificar se o Artin Sentinel está aberto; instalação cancelada." >&2
      return 3
    fi
    [[ -z "$pids" ]] && return 0
    echo "Artin Sentinel está aberto (PID: $pids)." >&2
    if [[ ! -t 0 ]]; then
      echo "Feche o aplicativo e execute ./install.sh novamente. --yes não substitui esta verificação." >&2
      return 3
    fi
    if ! read -r -p "Feche todas as janelas do Sentinel; pressione Enter para verificar novamente ou C para cancelar: " answer; then
      echo "Instalação cancelada; o aplicativo continua aberto." >&2
      return 3
    fi
    case "${answer,,}" in c|cancelar) echo "Instalação cancelada." >&2; return 3 ;; esac
  done
}

print_status() {
  local label="$1" cmd="$2" required="$3"
  if have "$cmd"; then
    printf '  %-12s OK   (%s)\n' "$label" "$(command -v "$cmd")"
  elif [[ "$required" == "1" ]]; then
    printf '  %-12s FALTA [essencial]\n' "$label"
  else
    printf '  %-12s FALTA [opcional]\n' "$label"
  fi
}

report_dependencies() {
  echo "Sistema: ${PRETTY_NAME:-${ID:-Linux}}"
  echo "Dependências do Artin Sentinel:"
  if python_ok; then
    printf '  %-12s OK   (%s)\n' "Python 3.12+" "$(python3 -c 'import sys; print(sys.version.split()[0])')"
  elif have python3; then
    printf '  %-12s FALTA [essencial] (encontrado %s)\n' "Python 3.12+" "$(python3 -c 'import sys; print(sys.version.split()[0])' 2>/dev/null || echo desconhecido)"
  else
    printf '  %-12s FALTA [essencial]\n' "Python 3.12+"
  fi
  if venv_ok; then
    printf '  %-12s OK\n' "python venv"
  else
    printf '  %-12s FALTA [essencial]\n' "python venv"
  fi
  print_status ffmpeg ffmpeg 1
  print_status ffprobe ffprobe 1
  print_status ffplay ffplay 1
  echo "  Verificação de vídeo local (codecs H.264/H.265, RTSP e quadro RGB24):"
  if have python3; then python3 "$ROOT/tools/check_media_runtime.py" || true; fi
  if [[ "$MINIMAL" -eq 0 ]]; then
    print_status pactl pactl 0
    print_status ping ping 0
    print_status ssh ssh 0
  fi
  if [[ -f "$DATA/vendor/intelbras-netsdk/libdhnetsdk.so" ]]; then
    echo "  NetSDK       OK   (persistente; opcional, necessário apenas para recursos Intelbras específicos)"
  else
    echo "  NetSDK       AUSENTE [opcional; pode ser importado pela interface]"
  fi
}

required_missing() {
  python_ok || return 0
  venv_ok || return 0
  have ffmpeg || return 0
  have ffprobe || return 0
  have ffplay || return 0
  media_ok || return 0
  return 1
}

optional_missing() {
  [[ "$MINIMAL" -eq 1 ]] && return 1
  have pactl || return 0
  have ping || return 0
  have ssh || return 0
  return 1
}

package_manager() {
  if have dnf; then echo dnf
  elif have apt-get; then echo apt
  elif have zypper; then echo zypper
  elif have pacman; then echo pacman
  else echo unknown
  fi
}

packages_for_missing() {
  local pm="$1"
  local -a p=()
  case "$pm" in
    apt)
      if ! have python3; then p+=(python3); fi
      if ! venv_ok; then p+=(python3-venv); fi
      if ! have ffmpeg || ! have ffprobe || ! have ffplay || decoders_missing; then p+=(ffmpeg); fi
      if [[ "$MINIMAL" -eq 0 ]] && ! have pactl; then p+=(pulseaudio-utils); fi
      if [[ "$MINIMAL" -eq 0 ]] && ! have ping; then p+=(iputils-ping); fi
      if [[ "$MINIMAL" -eq 0 ]] && ! have ssh; then p+=(openssh-client); fi
      ;;
    dnf)
      if ! have python3; then p+=(python3); fi
      # Fedora/RHEL-family: venv normalmente acompanha python3.
      if ! have ffmpeg || ! have ffprobe || ! have ffplay; then p+=(ffmpeg-free); fi
      # RPM Fusion complements Fedora's limited ffmpeg-free when enabled.
      if decoders_missing && dnf -q repoquery --available libavcodec-freeworld 2>/dev/null | grep -Eq '^libavcodec-freeworld([.-]|$)'; then
        p+=(libavcodec-freeworld)
      fi
      if [[ "$MINIMAL" -eq 0 ]] && ! have pactl; then p+=(pulseaudio-utils); fi
      if [[ "$MINIMAL" -eq 0 ]] && ! have ping; then p+=(iputils); fi
      if [[ "$MINIMAL" -eq 0 ]] && ! have ssh; then p+=(openssh-clients); fi
      ;;
    zypper)
      if ! have python3; then p+=(python3); fi
      if ! have ffmpeg || ! have ffprobe || ! have ffplay || decoders_missing; then p+=(ffmpeg); fi
      if [[ "$MINIMAL" -eq 0 ]] && ! have pactl; then p+=(pulseaudio-utils); fi
      if [[ "$MINIMAL" -eq 0 ]] && ! have ping; then p+=(iputils); fi
      if [[ "$MINIMAL" -eq 0 ]] && ! have ssh; then p+=(openssh-clients); fi
      ;;
    pacman)
      if ! have python3; then p+=(python); fi
      if ! have ffmpeg || ! have ffprobe || ! have ffplay || decoders_missing; then p+=(ffmpeg); fi
      if [[ "$MINIMAL" -eq 0 ]] && ! have pactl; then p+=(libpulse); fi
      if [[ "$MINIMAL" -eq 0 ]] && ! have ping; then p+=(iputils); fi
      if [[ "$MINIMAL" -eq 0 ]] && ! have ssh; then p+=(openssh); fi
      ;;
  esac
  printf '%s\n' "${p[@]}"
}

install_system_dependencies() {
  local pm
  pm="$(package_manager)"
  if [[ "$pm" == "unknown" ]]; then
    echo "Não foi possível identificar um gerenciador suportado (dnf/apt/zypper/pacman)."
    echo "Use --check e instale manualmente os itens marcados como essenciais."
    return 1
  fi

  mapfile -t pkgs < <(packages_for_missing "$pm" | awk 'NF && !seen[$0]++')
  if [[ "${#pkgs[@]}" -eq 0 ]]; then
    return 0
  fi

  echo
  echo "Pacotes do sistema necessários/recomendados: ${pkgs[*]}"
  if [[ "$NO_SYSTEM" -eq 1 ]]; then
    echo "--no-system ativo: nenhuma alteração de sistema será feita."
    return 0
  fi

  if [[ "$ASSUME_YES" -eq 0 ]]; then
    if [[ ! -t 0 ]]; then
      echo "Instalação não interativa: não vou chamar sudo automaticamente."
      echo "Rode novamente em um terminal ou use ./install.sh --yes."
      return 0
    fi
    read -r -p "Instalar esses pacotes agora com sudo? [S/n] " ans
    case "${ans:-S}" in
      s|S|sim|SIM|Sim|y|Y|yes|YES|Yes) ;;
      *) echo "Instalação de pacotes do sistema ignorada pelo operador."; return 0 ;;
    esac
  fi

  if ! have sudo; then
    echo "sudo não está disponível. Instale manualmente: ${pkgs[*]}" >&2
    return 1
  fi

  case "$pm" in
    apt)
      sudo apt-get update
      sudo apt-get install -y "${pkgs[@]}"
      ;;
    dnf)
      sudo dnf install -y "${pkgs[@]}"
      ;;
    zypper)
      sudo zypper --non-interactive install "${pkgs[@]}"
      ;;
    pacman)
      sudo pacman -S --needed --noconfirm "${pkgs[@]}"
      ;;
  esac
}

PREV_VERSION="$(installed_version)"
if [[ "$CHECK_ONLY" -eq 0 && -n "$PREV_VERSION" && "$ALLOW_DOWNGRADE" -eq 0 ]]; then
  relation="$(version_relation "$PREV_VERSION" "$NEW_VERSION")"
  if [[ "$relation" == "newer" || "$relation" == "unknown" ]]; then
    echo "ERRO: Artin Sentinel $PREV_VERSION já está instalado; este pacote é $NEW_VERSION." >&2
    echo "A instalação foi interrompida antes de alterar pacotes ou arquivos. Para voltar de versão intencionalmente, use --allow-downgrade." >&2
    exit 1
  fi
fi

if [[ "$CHECK_ONLY" -eq 1 ]]; then
  echo "Versão instalada: ${PREV_VERSION:-não encontrada}; versão deste pacote: $NEW_VERSION"
  report_dependencies
  echo
  if required_missing; then
    echo "Resultado: faltam dependências essenciais. --check não altera o sistema."
    exit 1
  else
    echo "Resultado: dependências essenciais disponíveis."
  fi
  exit 0
fi

# Check before installing system packages as well as before replacing Python.
if have python3; then
  require_sentinel_closed || exit $?
fi

# Antes de tocar no runtime do aplicativo, corrija dependências do sistema.
if required_missing || optional_missing; then
  report_dependencies
  install_system_dependencies || true
  echo
fi

# Python 3.12+ e venv são indispensáveis para instalar o aplicativo.
if ! python_ok; then
  echo "ERRO: Python 3.12+ não está disponível após a etapa de dependências." >&2
  exit 1
fi
if ! venv_ok; then
  echo "ERRO: módulo venv do Python não está disponível após a etapa de dependências." >&2
  exit 1
fi
if required_missing; then
  echo "ERRO: vídeo local indisponível (FFmpeg, H.264/H.265, RTSP ou RGB24)." >&2
  if [[ "$(package_manager)" == "dnf" ]]; then
    echo "No Fedora, instale ffmpeg-free; se faltarem codecs, configure um repositório de codecs confiável (ex.: RPM Fusion) e instale libavcodec-freeworld." >&2
  fi
  echo "Execute ./install.sh --check para identificar o componente ausente e depois repita a instalação." >&2
  exit 1
fi

require_sentinel_closed || exit $?

mkdir -p "$BIN" "$APPS" "$ICONS" "$(dirname "$VENV")"
if [[ ! -d "$VENV" ]]; then
  python3 -m venv "$VENV"
fi

"$VENV/bin/python" -m pip install --upgrade pip
"$VENV/bin/python" -m pip install --upgrade "$ROOT"

# Detecta bibliotecas nativas Qt ausentes antes de publicar um atalho inoperante.
if ! QT_QPA_PLATFORM=offscreen "$VENV/bin/python" - <<'PY'
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage
import keyring, cryptography
app = QApplication([])
image = QImage(16, 16, QImage.Format_RGB888)
assert not image.isNull()
app.quit()
PY
then
  echo "ERRO: PySide6/Qt não iniciou neste computador. Confira as bibliotecas nativas de Qt e execute o instalador novamente." >&2
  exit 1
fi

cp "$ROOT/artin_sentinel/resources/artin-sentinel.png" "$ICONS/artin-sentinel.png"

cat > "$BIN/artin-sentinel" <<EOF2
#!/usr/bin/env bash
exec "$VENV/bin/artin-sentinel" "\$@"
EOF2
chmod +x "$BIN/artin-sentinel"

cat > "$APPS/artin-sentinel.desktop" <<EOF2
[Desktop Entry]
Type=Application
Name=Artin Sentinel
Comment=Monitoramento e diagnóstico CFTV multimarcas
Exec=$BIN/artin-sentinel
Icon=artin-sentinel
Terminal=false
Categories=Network;Utility;
StartupNotify=true
StartupWMClass=artin-sentinel
EOF2
chmod +x "$APPS/artin-sentinel.desktop"

if have update-desktop-database; then update-desktop-database "$APPS" || true; fi
if have kbuildsycoca6; then kbuildsycoca6 --noincremental >/dev/null 2>&1 || true; fi
if have gtk-update-icon-cache; then gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" >/dev/null 2>&1 || true; fi

echo
echo "Validação das dependências após a instalação:"
report_dependencies

echo "  Qt/PySide6 e bibliotecas Python: OK"

# Intelbras NetSDK: instalação opcional separada, pelo menu de atualizações.
NETSDK_DIR="$DATA/vendor/intelbras-netsdk"
if [[ -f "$NETSDK_DIR/libdhnetsdk.so" && -f "$NETSDK_DIR/localRecordAudio.dav" ]]; then
  echo "Intelbras NetSDK: runtime persistente e referência 05.Talk já disponíveis"
elif [[ -f "$NETSDK_DIR/libdhnetsdk.so" ]]; then
  echo "Intelbras NetSDK: runtime local disponível; referência 05.Talk ausente."
  echo "  Use Configuração → Atualizações → Instalar / importar NetSDK Intelbras para completar o suporte."
else
  echo "Intelbras NetSDK: não instalado. O suporte pode ser importado pela interface em Configuração → Atualizações."
fi

echo
echo "Artin Sentinel $NEW_VERSION instalado/atualizado."
echo "Launcher: $BIN/artin-sentinel"
echo "Menu: $APPS/artin-sentinel.desktop"
echo "Ícone: $ICONS/artin-sentinel.png"

if [[ -n "$PREV_VERSION" && "$PREV_VERSION" != "$NEW_VERSION" ]]; then
  mkdir -p "$DATA"
  cat > "$DATA/pending-release-notes.json" <<EOF2
{"previous_version":"$PREV_VERSION","version":"$NEW_VERSION"}
EOF2
  if [[ -z "$(running_sentinel_pids)" ]]; then
    nohup "$BIN/artin-sentinel" >/dev/null 2>&1 &
    echo "Artin Sentinel reaberto após a atualização."
  else
    echo "O Sentinel já está em execução; as novidades aparecerão na próxima abertura."
  fi
fi
