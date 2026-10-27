# Artin Sentinel 0.2.94.38 — Equipamentos 2.0 + Titânio/Ciano

Instalador completo de teste para Fedora, Mint/Ubuntu e Arch Linux x86_64.

Esta candidata consolida o cadastro e a manutenção de equipamentos numa única experiência, sem alterar os motores proprietários já existentes.

- **Equipamentos 2.0:** Adicionar, dispositivo descoberto e Editar convergem para a mesma janela de cadastro/acesso.
- **Descoberta flutuante:** “Dispositivos localizados” não ocupa mais espaço permanente na tela Equipamentos.
- **Marca/tipo orientam o acesso:** Hikvision/HiLook usa HCNetSDK/ISAPI/RTSP quando aplicável; Intelbras/Dahua usa NetSDK/HTTP/RTSP; genéricos ficam em ONVIF/RTSP até homologação.
- **Salvar e validar acesso:** ao incluir ou alterar equipamento local, o Sentinel testa a credencial e inicia a leitura de canais/stream automaticamente.
- **Transferência segura:** opcionalmente leva credenciais em pacote `.asx` criptografado e restaura as senhas no cofre do PC de destino.
- **Titânio + Ciano:** escudo e ícones vetoriais próprios voltam a ser o padrão visual do Sentinel.
- **Hikvision:** mantém ISAPI/RTSP e HCNetSDK isolado, incluindo busca/reprodução/exportação de gravações.
- **Intelbras:** NetSDK, Cloud, Live View, reprodução e exportação da base anterior permanecem preservados.

Leia `docs/EQUIPMENT_ONBOARDING_029438.md` para o roteiro funcional desta candidata.

## Instalar

Feche o Sentinel, extraia o pacote em uma pasta e execute:

```bash
bash install.sh
```

Não use `sudo`. O instalador reaproveita o runtime, banco, SDKs e configurações existentes quando compatíveis.

## Exportar para outro PC

Em **Configuração → Exportar equipamentos…** selecione os Sites/equipamentos e escolha se deseja levar canais, nomes/apelidos, preferências de stream e layouts.

Há dois formatos:

- **Pacote seguro `.asx`**: pode incluir as credenciais disponíveis no cofre/sessão do Sentinel. O arquivo inteiro é protegido com AES-256-GCM e uma senha de transferência informada pelo operador. A senha de transferência não é gravada.
- **Inventário `.json`**: mantém a compatibilidade anterior e nunca inclui senhas/tokens.

Ao exportar com credenciais, o Sentinel avisa se algum equipamento selecionado não possui senha disponível. É possível continuar levando apenas as credenciais encontradas.

## Importar equipamentos

Em **Configuração → Importar equipamentos…** selecione `.asx` ou `.json`.

Para `.asx`, o Sentinel pede uma única senha de transferência, descriptografa o conteúdo em memória e regrava cada senha compatível no keyring/cofre local. Cadastros já existentes são reutilizados; não são duplicados.

Depois da importação:

- se a credencial foi restaurada, o Sentinel testa o acesso e atualiza canais/stream automaticamente;
- se faltar credencial, abre o fluxo de configuração somente para os equipamentos pendentes;
- conflitos de identidade continuam bloqueados para impedir associação ao equipamento errado;
- o Site operacional não é alterado apenas para administrar um equipamento importado.

A visão **Todos os Sites** em Configuração → Equipamentos permite localizar equipamentos importados de outro Site sem misturar os contadores/monitoramento do Site ativo.

> Arquivos JSON antigos que nunca continham senhas não podem recuperar essas senhas retroativamente. Para transportar credenciais, faça uma nova exportação `.asx` a partir de um Sentinel que ainda possua as senhas no cofre ou na sessão.
## Histórico da base

# Artin Sentinel 0.2.94.30 — Topway IP e estabilidade do Live View

Instalador completo de teste Linux x86_64: Fedora, Mint/Ubuntu e Arch.
Esta versão amplia o Sentinel; não altera o código do Artin NetLens.

## Correções desta versão

- Leitura complementar de `/ISAPI/ContentMgmt/InputProxy/channels`: mantém IDs e
  nomes reais das entradas IP quando Streaming/channels ou status estão vazios.
- IDs anunciados entre 1 e 256 são preservados mesmo acima do limite manual de
  busca. Exemplo: DVR de 16 entradas físicas com câmeras IP nos IDs 17 e 18.
  Estado ausente permanece pendente até a validação do fluxo, sem inventar Online.
- Abrir todos ignora entradas analógicas explicitamente sem sinal, preservando
  o comportamento legado para entradas cujo estado ainda é desconhecido.
- EOF imediato não é mais registrado como timeout de 15 segundos; o watchdog
  exige que o período de espera tenha realmente transcorrido.
- O processo de vídeo é encerrado antes de fechar seus pipes, permitindo que o
  leitor de diagnóstico termine. Cancelamento não fecha descritores em uso.
- Compatibilidade de protocolo para o modelo exato Topway DEFENDER 16-720T3,
  mantendo Topway como marca. Não equivale a homologar outros modelos ou todas
  as funções de reprodução. Cadastro abreviado pode usar protocolo Hikvision
  explicitamente, ou corrigir o campo Modelo para o modelo completo.

### Teste prioritário na Mallet

Leia `docs/TESTES_0.2.94.30.md`. Feche o Sentinel antes de atualizar. Após instalar,
leia novamente os canais do Topway: devem aparecer os IDs 17 e 18, sem renumerar.
O campo de busca pode permanecer em 16; IDs anunciados pelo DVR têm precedência.
Abra apenas o canal 18 primeiro. A validação física desta build ainda é necessária.
Não altere portas nem autenticação do DVR para este teste. Neste firmware,
alternar RTSP provocou reinicialização completa; não é necessário repetir.

## Recursos preservados da .29

- **Configurações → AKDB → Fabricantes e cores:** nome padronizado, aliases e
  paleta. Intelbras verde, Positivo azul, Hikvision vermelho, JFL amarelo,
  Haiz laranja e AikTec azul-claro. Aitek permanece fabricante separado;
  não foi cadastrado como alias de AikTec sem evidência de equivalência.
- Somente a marca após “·” recebe cor, nas árvores principal e adicionais.
  Nome amigável, canais e bolinhas de conexão são preservados. Marcas desconhecidas
  usam cor neutra. Cores são pintadas localmente, sem consultas à rede por item.
- **Explorar modelos:** marca → tipo → modelo, filtros e ficha de protocolos,
  capacidades e validações. O estado geral do perfil não valida cada recurso.
  Sem evidência individual, a função aparece pendente/conhecida no perfil.
  Firmware ou data não registrados não são inventados.
- **Adicionar / Editar identificação:** referência opcional AKDB preenche campos
  vazios de fabricante, modelo, tipo e protocolo. Dados preenchidos divergentes
  bloqueiam aplicar a referência; IP, URLs, credenciais e recursos não são confirmados.
- A descoberta registra evidência observada, origem, horário e referência AKDB.
  Sugestões de portas e capacidade ficam identificadas como candidatas; os valores
  reais exigem consulta do aparelho. Conflitos de marca/perfil e de identificadores
  físicos não devem atualizar silenciosamente o cadastro conhecido.
- **Hikvision:** cancelamento do calendário entre páginas, reconhecimento de MATCHES,
  detecção de páginas repetidas e preservação de resultados parciais em vários canais.
  Diagnóstico mostra páginas, trechos e duração, sem retornar URLs ou credenciais.

Preferências de fabricantes usam tabelas locais adicionais na AKDB existente,
sem aumentar o schema Core, promover homologação ou enviar modificações à Internet.
São aplicadas neste PC; não entram na transferência de equipamentos da .27.
A futura integração do NetLens será feita no projeto dele. Perfis oficiais,
evidências e preferências locais continuam separados.

## Instalar

Feche o Sentinel, extraia o pacote em pasta separada e execute:

```bash
bash install.sh
```

Os caminhos dnf/apt/pacman e os dados existentes são preservados. Não há dependência
nova. Runtime, NetSDK e ponte Wine válidos continuam sendo reaproveitados.

## Transferência nas versões históricas

As notas abaixo descrevem comportamentos de versões anteriores. A 0.2.94.38 substitui o fluxo antigo pela transferência segura descrita no início deste README. O JSON legado continua disponível sem credenciais.
## Próxima rodada: Hikvision e HiLook

A validação de campo será feita na Mallet. Consulte
`docs/TESTES_0.2.94.29.md` para o roteiro desta versão e
`docs/HIKVISION_HILOOK_VALIDACAO.md` para a rodada por fabricante. O teste local da transferência usa SQLite e
mídia sintética; não substitui o teste com os gravadores reais.
