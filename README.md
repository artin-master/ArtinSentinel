# Artin Sentinel 0.2.94.32 — acesso, componentes e vídeo

Instalador completo de teste para Fedora, Mint/Ubuntu e Arch, Linux x86_64.

- **Configuração → Componentes e SDKs…**: instalação, carga local, versões e sessões.
- **Diagnóstico e atividade…**: erros e acesso efetivamente utilizado.
- Cadastro orientado pela marca, menus agrupados e indicadores de codec/resolução.
- Hikvision SDK: prévia Main 720p, aceleração nativa até 8× e exportação Original/Compacto.
- Exportação confere vídeo/duração antes de publicar e informa o caminho final.

Leia o [roteiro completo de teste](docs/TESTES_0.2.94.32.md).
Aceleração e exportação Hikvision SDK precisam de confirmação no DVR físico.
Áudio de escuta por esse SDK, Substream do aparelho de teste e Hik-Connect permanecem pendentes.
Os acessos existentes não são migrados automaticamente. O SDK oficial não acompanha o ZIP.

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

## Exportar para outro PC

Em **Configuração → Exportar equipamentos…**:

1. Se o controle de permissões estiver ativo, entre como administrador.
2. Marque os Sites/DVRs/câmeras que deseja levar. Um Site sem equipamentos marcados
   não entra no arquivo. Os equipamentos arquivados não são exportados nesta tela.
3. Escolha se deseja incluir canais, nomes/apelidos, preferências de stream e layouts.
   Canais inclui os canais cadastrados dos equipamentos marcados. Layouts ficam
   desmarcados por padrão; suas posições só referenciam os equipamentos selecionados.
4. Salve o arquivo JSON e leve-o ao PC de destino.

A identificação, endereço, portas conhecidas, serial, MAC e UUID disponíveis
acompanham o inventário. Nomes/apelidos são opcionais; nomes dos Sites organizam o
arquivo. Senhas de DVR, tokens, senhas de operador/administrador, permissões e URLs
de vídeo não entram no arquivo. O JSON é gravado com acesso restrito ao usuário local.

## Importar somente os novos

**Atualize o Sentinel dos dois PCs para .27 ou posterior.** O formato novo é
`artin-sentinel-portable-v2`; versões anteriores podem recusá-lo. A .27 também
aceita o formato v1 dos arquivos antigos.

Em **Configuração → Importar equipamentos…**, escolha o JSON. A prévia não faz
escritas nem conexões com DVRs. Ela mostra:

- **Novo:** pode ser marcado para inclusão.
- **Já cadastrado:** será preservado, inclusive seus canais, nomes e credenciais.
- **Conflito:** será ignorado para evitar escolher automaticamente o equipamento errado.

A comparação usa serial, UUID e MAC válidos quando presentes, além de Site,
endereço, fabricante/modelo e portas. IP igual em Sites diferentes não significa
necessariamente o mesmo equipamento. Identificadores divergentes, Sites arquivados
ou ambíguos e identidades repetidas no próprio arquivo geram conflitos. Quando
faltam identificadores, um endereço já ocupado no Site é tratado de forma conservadora.

Desmarque os novos que não deseja incluir e clique **Importar N novo(s)**.
Equipamentos já existentes não recebem canais novos ou alterações de configuração.
Nenhum equipamento ou Site arquivado é restaurado automaticamente. Reimportar o
mesmo arquivo não duplica o que já foi incluído.

Layouts existentes não são sobrescritos. Layouts ausentes referenciam apenas os
novos equipamentos importados; posições de cadastros não incluídos ficam vazias.
O inventário é revalidado na confirmação; se mudou desde a prévia, abra a prévia
novamente. Erro de gravação no banco desfaz a importação inteira.

Após importar, informe as credenciais no destino e faça a leitura/validação dos
canais. Equipamentos e canais chegam sem confirmação de acesso e sem imagem
marcada como validada. Modos local, rede privada/conector e Cloud Intelbras são
preservados quando disponíveis no arquivo v2; dependências e túneis do PC de origem
não são transferidos. Um conector/ponte externo precisa ser preparado no destino.

## Próxima rodada: Hikvision e HiLook

A validação de campo será feita na Mallet. Consulte
`docs/TESTES_0.2.94.29.md` para o roteiro desta versão e
`docs/HIKVISION_HILOOK_VALIDACAO.md` para a rodada por fabricante. O teste local da transferência usa SQLite e
mídia sintética; não substitui o teste com os gravadores reais.
