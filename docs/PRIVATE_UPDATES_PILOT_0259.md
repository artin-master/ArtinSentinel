# Atualizações privadas — piloto 0.2.59

## Fluxo

O PC da rede do operador guarda os ZIPs e executa `tools/private_update_origin.py` em `127.0.0.1:18888`. Uma conexão SSH **iniciada pelo PC** encaminha a porta para `127.0.0.1:18889` em um servidor externo. Caddy recebe `https://updates.seu-dominio` e encaminha as requisições à porta de loopback no servidor externo. O próprio serviço confere a chave individual de cada cliente antes de entregar manifesto ou ZIP. Nenhuma porta do DVR é usada.

O servidor externo e o domínio precisam ser provisionados antes do teste com clientes. Não aponte o DNS para o PC residencial. SSH e Caddy devem ser configurados para reiniciar com o sistema e monitorados; caso contrário, a atualização fica indisponível quando o túnel cai.

## Preparação no PC da origem (terminal local)

```bash
python3 tools/private_update_origin.py --root "$HOME/.local/share/artin-update-origin" issue cliente_teste
python3 tools/private_update_origin.py --root "$HOME/.local/share/artin-update-origin" publish ArtinSentinel_0.2.59_private_updates_pilot.zip --base-url https://updates.seu-dominio
python3 tools/private_update_origin.py --root "$HOME/.local/share/artin-update-origin" serve --port 18888
```

Guarde a chave impressa pelo comando `issue` fora de arquivos compartilhados; ela aparece apenas uma vez. Para cancelar o acesso sem mudar as chaves dos outros clientes:

```bash
python3 tools/private_update_origin.py --root "$HOME/.local/share/artin-update-origin" revoke cliente_teste
```

O comando `publish` grava o pacote e substitui o manifesto *local* depois de conferir o ZIP. Isso não publica no GitHub nem altera o ArtinUpdates público. Use um nome de arquivo novo para cada pacote. Cada cliente precisa instalar a 0.2.59 manualmente uma vez, salvar sua URL HTTPS e chave individual em **Configuração → Atualizações** e então poderá verificar/instalar versões futuras por esse canal.

## Exemplo de encaminhamento no servidor externo

No PC de origem, com conta SSH dedicada no servidor externo (endereço e chaves sob controle do operador):

```bash
ssh -NT -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -R 127.0.0.1:18889:127.0.0.1:18888 operador@servidor-exemplo
```

No Caddyfile do servidor externo, **substitua pelo domínio real** que aponta ao servidor:

```text
updates.seu-dominio {
    reverse_proxy 127.0.0.1:18889
}
```

Restringir o usuário SSH a esse encaminhamento e manter a porta encaminhada apenas em loopback. HTTPS deve ter certificado válido; nunca use endereço HTTP para inserir chave no app. A configuração final do servidor e firewall depende do host contratado e ainda não foi testada remotamente.

## Limites deste piloto

- Testes automatizados verificam autenticação, revogação, manifesto, ZIP e isolamento do servidor; não validam o túnel, Caddy, DNS ou hardware físico.
- O operador precisa manter o PC e o servidor ligados. O serviço Python é um protótipo de origem, idealmente executado sob uma conta Linux própria com diretório privado e supervisão do sistema.
- SHA-256 confere integridade do pacote; o serviço privado e o TLS são a origem de confiança até ser provisionada uma chave pública Ed25519 no Sentinel. A chave do cliente não deve ser colocada no manifesto ou na URL.
