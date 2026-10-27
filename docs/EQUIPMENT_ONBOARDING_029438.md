# Artin Sentinel 0.2.94.38 — Equipamentos 2.0

## Objetivo

Reduzir o cadastro/manutenção de DVR, NVR, XVR e câmeras IP a um único fluxo operacional:

**identificar → informar acesso → validar → ler canais → salvar pronto para uso**.

A versão parte da 0.2.94.33 e preserva os providers, SDKs e caminhos de mídia já existentes.

## Tela Equipamentos

A tela fixa mantém o inventário e os detalhes do equipamento. A descoberta de rede deixa de ocupar espaço permanente.

O botão **Adicionar** abre o painel flutuante **Localizar equipamentos na rede**. Nesse painel há:

- **Buscar / atualizar**;
- **Adicionar por endereço**;
- **Usar selecionado** para um resultado descoberto;
- ações auxiliares de Web/AKDB.

Todos os caminhos convergem para o mesmo editor de equipamento.

## Cadastro e manutenção unificados

Adicionar manualmente, usar um equipamento descoberto e editar um equipamento existente usam a mesma janela.

Campos principais:

- Site;
- nome amigável;
- IP/host;
- tipo;
- fabricante/modelo;
- origem do acesso;
- usuário/senha;
- salvar no cofre;
- portas Web/RTSP/SDK;
- quantidade de canais a validar.

O botão principal é **Salvar e validar acesso**. Para equipamento local ele grava/atualiza o mesmo cadastro, aplica a credencial e inicia imediatamente a leitura de canais/stream. O botão **Canais** permanece disponível apenas como manutenção/revalidação posterior.

## Política por marca

A marca/tipo determina as opções válidas:

- **Hikvision/HiLook DVR/NVR/XVR**: HCNetSDK/ISAPI/RTSP; porta SDK padrão 8000;
- **Intelbras/Dahua DVR/NVR/XVR**: NetSDK/HTTP/RTSP; porta SDK padrão 37777;
- **Intelbras Cloud**: disponível apenas quando Intelbras + gravador;
- **câmeras IP/genéricos/OEM**: ONVIF/RTSP e provider homologado;
- SDK proprietário incompatível fica bloqueado.

A política de tela não declara uma capability como homologada; o teste real continua obrigatório.

## Transferência segura de credenciais

A exportação de equipamentos pode gerar:

- **JSON**: inventário sem senha, compatível com o fluxo anterior;
- **ASX**: pacote criptografado com inventário + credenciais disponíveis.

O ASX usa:

- AES-256-GCM para criptografia autenticada;
- scrypt N=32768/r=8/p=1 para derivação da chave;
- salt e nonce aleatórios;
- uma senha de transferência informada pelo operador.

As senhas dos DVRs não aparecem em texto aberto no arquivo, SQLite, argumentos de processo ou logs. No computador de destino, as credenciais são descriptografadas em memória, associadas ao cadastro não conflitante e regravadas no keyring/cofre local.

Quando a credencial foi restaurada, o onboarding pós-importação usa essa credencial automaticamente para testar o acesso e atualizar os canais, sem pedir novamente a senha de cada gravador.

## Identidade visual

A versão restaura a identidade **Titânio + Ciano** aprovada:

- escudo/sentinela vetorial;
- ícones operacionais metálicos com acento ciano;
- estados normal/hover/pressionado/selecionado;
- ícones próprios em Ao Vivo, Reprodução e Equipamentos.

Os elementos são vetoriais para manter consistência em Linux/Windows e HiDPI.

## Preservação de providers

A 0.2.94.38 não altera os motores centrais Intelbras Cloud, Intelbras Cloud Recordings, Intelbras Local Playback e Intelbras NetSDK.

Hikvision ISAPI/HCNetSDK e Intelbras NetSDK/Cloud continuam separados por provider.

## Validação física necessária

1. abrir Equipamentos e confirmar o ganho de espaço;
2. usar Adicionar → busca de rede e cadastro por endereço;
3. cadastrar/editar um Intelbras e confirmar NetSDK/porta 37777;
4. cadastrar/editar um Hikvision e confirmar HCNetSDK/porta 8000;
5. verificar teste automático e canais sem botão extra;
6. exportar um conjunto com credenciais em ASX e importar em outro Sentinel;
7. confirmar ausência de duplicação e atualização automática dos canais;
8. conferir os novos ícones Titânio + Ciano no Ao Vivo/Reprodução/Equipamentos;
9. testar gravação Hikvision e regressão Intelbras.
