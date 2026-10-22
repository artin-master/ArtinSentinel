# Piloto 0.2.50: MHDX 1004 em outro local

O DVR permanece na rede 192.168.15.254 e não precisa de portas públicas. Um computador Linux ligado no mesmo Site inicia SSH de saída até um servidor intermediário (relay) administrado pelo operador. A estação Sentinel inicia outro SSH até o mesmo relay. O acesso usa a credencial do **DVR**, solicitada na leitura de canais; o SSH usa chaves separadas. É uma alternativa de conectividade para teste; não é integração ao Intelbras Cloud por serial.

| Serviço do DVR | Porta no relay (somente loopback) | Porta na estação Sentinel (somente loopback) |
| --- | ---: | ---: |
| HTTP 80 | 24080 | 18080 |
| RTSP 554 | 24554 | 18554 |
| Serviço 37777 | 27777 | 37777 |

## Requisitos e preparação

1. Separe um computador Linux que permaneça ligado na rede do DVR, com Python 3 e cliente `ssh` OpenSSH. Da máquina, confira TCP 80, 554 e 37777 em 192.168.15.254. Se o DVR estiver em portas diferentes, use `--dvr-http-port`, `--dvr-rtsp-port` e `--dvr-service-port` no comando do Site.
2. Prepare um servidor Linux com endereço público e `sshd` sob seu controle. Ele precisa aceitar SSH de saída vindo do Site e do computador Sentinel. Use contas dedicadas (`site1` e `operator1`), cada uma com sua chave exclusiva. Não reutilize a senha do DVR. Confirme a chave pública do servidor por um canal confiável antes da primeira conexão; o script impõe `StrictHostKeyChecking=yes`.
3. Para reduzir o alcance de cada conta, restrinja o encaminhamento no `sshd_config` do **relay**. Ajuste caminhos e outras políticas existentes conforme seu servidor:

   ```text
   GatewayPorts no
   Match User site1
       PasswordAuthentication no
       AllowTcpForwarding remote
       PermitListen 127.0.0.1:24080 127.0.0.1:24554 127.0.0.1:27777
       PermitTTY no
       X11Forwarding no
       AllowAgentForwarding no
   Match User operator1
       PasswordAuthentication no
       AllowTcpForwarding local
       PermitOpen 127.0.0.1:24080 127.0.0.1:24554 127.0.0.1:27777
       PermitTTY no
       X11Forwarding no
       AllowAgentForwarding no
   ```

   Valide o arquivo com `sudo sshd -t` antes de recarregar o serviço. Use um relay reservado aos operadores de confiança: outros usuários locais do relay poderiam acessar seus listeners `127.0.0.1`. Use chaves SSH protegidas e não envie chaves privadas, senha ou serial do DVR.

4. Gere as duas chaves **em seus próprios computadores** com `ssh-keygen -t ed25519 -f ~/.ssh/sentinel_site1 -C sentinel-site1` no Site e `ssh-keygen -t ed25519 -f ~/.ssh/sentinel_operator1 -C sentinel-operator1` na estação. Instale **somente** cada `.pub` no `authorized_keys` da conta correspondente no relay. Registre a identidade do servidor SSH em `~/.ssh/known_hosts` depois de verificar a fingerprint fora de banda.

## Iniciar os dois túneis

Copie a pasta do projeto ou pelo menos `tools/site_tunnel.py` para o PC do Site. Os dois processos abaixo ficam em primeiro plano; para uso contínuo após o piloto, configure supervisão por `systemd` com usuário sem privilégios, reinício automático e segredos apenas no armazenamento local de chaves.

No computador Linux do **Site**:

```bash
python3 tools/site_tunnel.py site --relay SEU_RELAY --ssh-user site1 \
  --identity ~/.ssh/sentinel_site1 --dvr 192.168.15.254
```

Na estação com **Sentinel**, em outro terminal:

```bash
python3 tools/site_tunnel.py operator --relay SEU_RELAY --ssh-user operator1 \
  --identity ~/.ssh/sentinel_operator1
```

Use `--ssh-port N` se o relay não usar porta 22. Para conferir sintaxe sem conectar, acrescente `--dry-run`. Para host key exclusiva, use `--known-hosts CAMINHO`. Erros de chave desconhecida, credencial recusada ou porta ocupada aparecem no terminal SSH. O Site precisa de conexão de saída com o relay; a estação Sentinel também.

## Cadastrar e verificar

1. Na versão 0.2.50 do Sentinel, crie o Site de teste. Em **Configuração → Equipamentos → Adicionar**, escolha **Outro local • conector por Site (piloto)**, tipo **DVR / Multi HD**, protocolo **Intelbras / Dahua**, IP/host `127.0.0.1`, Web URL `http://127.0.0.1:18080` e RTSP URL `rtsp://127.0.0.1:18554`.
2. Rode **Diagnosticar**. HTTP e RTSP devem responder. Ping em `127.0.0.1` é apenas o próprio computador, por isso a indicação *online* usa as URLs encaminhadas.
3. Rode **Canais / Testar stream** com o usuário e senha do próprio MHDX. Confirme individualmente canais 1–4 e o canal IP 5, se equipado, comparando cenas ao vivo; abra um canal em **Ao vivo** e confira reconexão após interromper/restaurar ambos os túneis. Uma imagem repetida não homologa outro canal.
4. Se HTTP funcionar e RTSP falhar, confirme porta RTSP e autenticação do MHDX. Se ambos falharem, confira a saída dos dois processos SSH e o IP/portas do DVR no Site. Se o relay indicar *remote port forwarding failed*, revise `PermitListen` e se as portas já estão ocupadas.

Cada Site adicional exige portas exclusivas no relay e na estação (`--relay-http`, `--relay-rtsp`, `--relay-service`, `--local-http`, `--local-rtsp`, `--local-service`). Cadastre URLs com as portas daquele Site. Na mesma estação, cadastros com IP `127.0.0.1` em **Sites diferentes** podem compartilhar identidade internamente; para o piloto faça **um Site externo por vez**. Antes de ampliar para clientes, será necessário resolver identidade multi Site, reconexão supervisionada e validação real de cada fabricante. Não há teste físico offsite nesta entrega.
