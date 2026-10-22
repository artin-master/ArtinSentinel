# Testes de campo — Artin Sentinel 0.2.94.29

Instale com o Sentinel fechado: extraia e execute `bash install.sh`.
Não é necessário remover cadastros, prefixo Wine ou SDK já funcionando.

## 1. Identificação visual e persistência

- Conferir Intelbras verde, Hikvision vermelho e demais marcas conhecidas.
- Somente fabricante depois do separador tem cor; nome amigável/canais não mudam.
- Configurações → AKDB → Fabricantes e cores. Escolher uma marca, alterar a cor
  na paleta e salvar. Conferir árvore principal e janela de monitoramento adicional.
- Fechar/reabrir Sentinel: a preferência deve persistir.
- Se controle de acesso estiver ativo, operador não pode editar fabricantes.
- Cor muito escura ou alias pertencente a outra marca deve ser recusado sem salvar.

## 2. Catálogo e cadastro assistido

- AKDB → Explorar modelos. Filtrar Hikvision e localizar DS-7216HGHI-F1.
- Conferir tipos/modelos, protocolos, origem e estados individuais. Validação geral
  não significa aprovação de áudio, gravações ou exportação. Firmware desconhecido
  deve continuar explicitamente não individualizado.
- Adicionar um equipamento de teste por IP. Escolher referência AKDB e preencher
  campos vazios. IP, Web URL e RTSP URL não devem ser inventados pelo catálogo.
- Repetir em Editar identificação com campos já preenchidos: a referência não
  sobrescreve ajustes e deve avisar se marca/modelo forem divergentes.
- Não crie cadastros duplicados apenas para testar; cancelar o diálogo não salva nada.

## 3. Descoberta e identidade

- Fazer uma busca e conferir os dados de identificação/evidência e a origem AKDB.
- Comparar o aparelho no acesso Web: marca, modelo, tipo e capacidade conhecida.
- Conferir que nomes manuais e canais já cadastrados permanecem.
- Não alterar IP/MAC do ambiente operacional para forçar conflito. Casos de IP
  reutilizado e identificadores diferentes foram simulados em testes automatizados;
  reproduzir em campo somente com equipamento/reserva e janela de manutenção própria.
- Cadastro antigo sem origem detalhada deve informar essa ausência, sem parecer
  uma leitura nova do equipamento.

## 4. Gravações Hikvision — prioridade

- No DVR com gravações conhecidas, escolher canal e dia. Conferir agenda e régua.
- Reproduzir 1× por 2 minutos; conferir horário e continuidade de imagem.
- Clicar em outro horário, pausar/retomar e testar 2×, 4× e 8×.
  Referência: 1 minuto de gravação em 4× corresponde a cerca de 15 s;
  em 8×, cerca de 7,5 s, desconsiderando o carregamento inicial.
- Habilitar áudio onde exista captação: imagem deve continuar e som ser coerente.
- Exportar trecho de 1 minuto, original/compacto, com e sem áudio.
  Abrir o arquivo em outro player e conferir duração, imagem e som.
- Se o calendário for cancelado, não deve iniciar consultas novas; uma consulta
  já enviada pode aguardar o timeout HTTP de até 8 s.
- Um dia realmente vazio deve ser distinto de HTTP 401/403/404 ou falha de leitura.
- Copiar do Painel técnico as linhas de pesquisa/reprodução/exportação se falhar;
  informar modelo, firmware, canal, data e horário, sem credenciais.
- DVR sem câmeras: conferir cadastro e aviso sem canais, preservando inventário anterior.

## 5. Regressão Intelbras

- Abrir câmera local e Cloud juntas, trocar Main/Sub, fechar/reabrir um canal.
- Pesquisar um dia, reproduzir com áudio, saltar na régua e alternar 1×/4×/8×.
- Exportar um minuto com/sem som e confirmar arquivo externo.
- Conferir restauração do layout e uma janela adicional.

## Limites desta entrega

Nenhum novo DVR físico foi testado no ambiente de desenvolvimento. A rotina
Hikvision usa ISAPI + URI RTSP retornada pelo gravador; não acrescenta HCNetSDK,
Cloud proprietária nem garante que um firmware envie mídia acima de 1×.
As opções de reprodução são compartilhadas, mas o comportamento real precisa
ser confirmado por modelo. Homologação não é promovida por cor ou por cadastro.
