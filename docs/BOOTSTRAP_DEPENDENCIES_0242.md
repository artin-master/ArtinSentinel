# Bootstrap Dependencies — 0.2.42

A 0.2.42 introduz um bootstrap de dependências de sistema para primeira instalação e PCs de campo.

## Dependências essenciais

- Python 3.12+
- módulo `venv`
- `ffmpeg`
- `ffprobe`
- `ffplay`

## Dependências recomendadas

- `pactl` para controle de volume dinâmico
- `ping` para alguns diagnósticos de rede

## Gerenciadores suportados

- Fedora/RHEL: dnf
- Debian/Ubuntu/Linux Mint: apt
- openSUSE: zypper
- Arch/Manjaro: pacman

O instalador nunca deve ser executado como root. `sudo` é usado apenas, e com consentimento, para pacotes do sistema. `--check` é estritamente não destrutivo.
