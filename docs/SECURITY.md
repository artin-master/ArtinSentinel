# Segurança

O Artin Sentinel permanece orientado a operação **somente leitura** nesta fase.

## Equipamentos

- não envia comandos de configuração;
- não atualiza firmware;
- não reinicia equipamentos;
- não altera gravação;
- não expõe portas automaticamente;
- RTSP é usado para leitura/decodificação de vídeo;
- timeouts e tentativas de rede são limitados.

## Credenciais — 0.1.7

A 0.1.7 adiciona persistência opcional segura:

- o **usuário** pode ficar no SQLite;
- a **senha nunca é gravada no SQLite**;
- quando “Salvar credencial com segurança” é marcado, a senha é entregue ao `keyring` do sistema operacional;
- se não houver backend seguro disponível, o Sentinel **não** usa arquivo/texto puro como fallback;
- nesse cenário a senha permanece apenas em memória até o aplicativo ser fechado;
- a ação **Esquecer credencial** remove a associação e solicita remoção do segredo do keyring;
- senhas e URLs autenticadas não são escritas nos logs do Sentinel.

## Live View

O processo FFmpeg recebe temporariamente a credencial em runtime para autenticar o RTSP. A aplicação não persiste nem registra esse argumento. Essa integração deve continuar sendo revisada antes de uma versão Stable, especialmente para ambientes multiusuário onde a visibilidade de argumentos de processos locais seja uma preocupação.

## Thread safety

A decodificação ocorre fora da thread principal. Somente a thread Qt cria `QImage/QPixmap` e atualiza widgets. O padrão evita reintroduzir o crash nativo corrigido na 0.1.5.
