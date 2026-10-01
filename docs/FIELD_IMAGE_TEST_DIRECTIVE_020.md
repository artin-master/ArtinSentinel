# Artin Sentinel 0.2.0 — Diretiva de Testes de Imagem

## Ambiente prioritário

Equipamento de referência atual:

- Intelbras MHDX 1004
- IP de laboratório: 192.168.15.254
- 4 canais já confirmados por RTSP/ffprobe
- H.264 1280x720 confirmado nos quatro canais

A credencial não deve ser registrada neste documento, screenshots ou logs.

## Teste A — restauração do workspace

1. Abrir o Sentinel.
2. Selecionar mosaico 4.
3. Colocar os canais 01–04 nas janelas 1–4.
4. Fechar o aplicativo normalmente.
5. Abrir novamente.

**PASS:** grade 4 e canais reaparecem nas mesmas posições.

**PASS com atenção:** canal indisponível permanece na posição mostrando Offline/Sem vídeo; os demais não devem mudar de posição.

## Teste B — Substream

1. Clicar com botão direito no Canal 01.
2. Escolher `Abrir com stream → Substream`.
3. Abrir `Diagnóstico do Live View`.

Registrar screenshot do mosaico + painel técnico.

**PASS:** primeiro frame aparece e rodapé informa Substream.

**FAIL útil:** painel registra erro sanitizado suficiente para identificar endpoint/perfil/decoder.

## Teste C — Main stream

Repetir o teste B escolhendo Main stream.

**PASS:** vídeo aparece e rodapé informa Main stream.

## Teste D — Automático/fallback

1. Configurar Canal 01 como Automático.
2. Usar mosaico 4.
3. Se o substream falhar, observar o painel de diagnóstico.

**PASS:** Sentinel registra falha do Substream e tenta Main stream automaticamente sem intervenção.

Em visualização única, a preferência se inverte: Main primeiro, Sub como fallback.

## Teste E — troca de stream durante Live View

Com imagem ativa:

1. botão direito no quadro;
2. `Stream → Main stream`;
3. depois `Stream → Substream`;
4. voltar a `Automático`.

**PASS:** a troca reinicia somente aquele quadro e a GUI continua responsiva.

## Teste F — nomes amigáveis

- gravador: `DVR Casa`;
- Canal 01: apelido manual, ex. `Portão`;
- demais canais: manter nome recebido do DVR ou nome padrão.

**PASS:** árvore, cabeçalho do quadro e restauração do layout utilizam o nome amigável, enquanto IP/modelo permanecem nos detalhes.

## Teste G — credencial persistente

1. salvar credencial com segurança;
2. fechar o Sentinel;
3. abrir novamente.

**PASS:** o layout é restaurado e os streams tentam reconectar sem nova solicitação de senha.

**FAIL seguro:** se o keyring não estiver disponível, solicitar credencial; nunca salvar senha em texto puro.

## Teste H — falha e recuperação

Durante Live View:

1. interromper temporariamente um canal/equipamento por meio normal de laboratório;
2. observar estado do quadro;
3. restaurar a disponibilidade.

**PASS:** quadro permanece no mesmo slot, mostra falha/reconexão e recupera vídeo automaticamente.

## Evidências a guardar por teste

- screenshot do mosaico;
- screenshot do painel Diagnóstico quando houver falha;
- modo de stream ativo;
- hora do teste;
- modelo/firmware do equipamento;
- resultado PASS/FAIL;
- observação curta.

Nunca guardar senha, token ou URL contendo credencial.
