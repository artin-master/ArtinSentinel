# Teste de campo — AKDB compartilhada 0.2.15

## 1. Instalação

Atualize normalmente com `./install.sh` e abra o Sentinel.

## 2. Confirmar a AKDB Core

Abra **Configuração → AKDB**. No topo devem aparecer:

- indicação de que a AKDB é compartilhada entre Sentinel, NetLens e RescNow;
- quantidade de identidades centrais;
- quantidade de evidências de campo;
- caminho `~/.local/share/artin/akdb/akdb.sqlite3`;
- colunas `AKDB ID`, `Tipo de equipamento`, `Domínios` e `Origem / revisão`.

## 3. Registrar uma evidência candidata

Em **Configuração → Equipamentos**, selecione um equipamento e use **Exportar perfil AKDB**. O JSON continua sendo salvo onde o operador escolher e, adicionalmente, uma evidência sanitizada deve ser registrada na base compartilhada.

Volte à aba AKDB e reabra o Sentinel caso necessário. O contador de evidências deve aumentar. Isso **não** muda o equipamento para homologado automaticamente.

## 4. Regressão física

A 0.2.15 não substitui os testes pendentes da 0.2.14. Revalidar:

1. Hikvision DS-7216HGHI-F1 classificado/roteado como DVR;
2. enumeração `/Streaming/Channels/{canal}01/02`;
3. áudio real em Live View;
4. console PTZ/Speed Dome IT-Blue.

## 5. ARN / ANL

Nesta build apenas o Sentinel já está conectado ao novo core. ARN e ANL usarão o mesmo `stable_id`, schema e SQLite quando receberem seus adaptadores. Não é necessário criar outra base AKDB para eles.
