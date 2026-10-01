# 0.2.54 — Cadastro por modelo e leitura de canais

## Origem da capacidade

A extensão Sentinel da AKDB define o limite de posições para cada perfil concreto. O MHDX 1004 possui quatro entradas analógicas e uma posição IP (cinco no total); NVD 1416, NVD 1516 e MHDX 1216 têm 16 posições candidatas. A resolução consulta primeiro o modelo informado, depois o nome e então o perfil AKDB associado. Uma associação antiga ao MHDX 1004 feita somente pelo fabricante não limita outro gravador a cinco posições.

O diálogo **Canais / Testar stream** mostra a capacidade sugerida e a chave AKDB. Uma alteração manual fica marcada no cadastro do gravador como `channel_scan_source=manual`; a seleção do padrão é `akdb`. Cadastros antigos que guardaram cinco posições sem registrar a origem passam a usar 16 quando o modelo NVD 1416, NVD 1516 ou MHDX 1216 é reconhecido. Ajustes manuais explícitos continuam prevalecendo.

## Inventário e validação

A aba **Equipamentos** exibe a busca de novos dispositivos acima dos já cadastrados. A detecção não adiciona automaticamente credenciais nem valida vídeo; **Adicionar selecionado** aproveita o fluxo de cadastro existente. A coluna Canais apresenta posições listadas, capacidade conhecida e quantas têm mídia validada.

O prazo da leitura Intelbras acompanha a quantidade de posições. Quando a verificação RTSP excede o tempo, a busca devolve as posições restantes com estado **RTSP ainda não testado**. Esses registros não entram como vídeo disponível. Um resultado parcial não substitui uma rota antiga confirmada por uma falha temporária e não torna indisponíveis os canais que não chegou a testar. O operador pode repetir a leitura e consultar a coluna Evidência para distinguir inventário do modelo de vídeo real.

## Teste no equipamento

No Site correto, selecione o NVD 1416, confirme o perfil na área de detalhes e abra **Canais**. Confira o padrão de 16 posições e inicie a leitura. Compare o número de posições listadas com as que têm vídeo confirmado. Caso ainda não haja mídia, a capacidade AKDB não resolve autenticação, caminho RTSP ou bloqueio da rede; consulte a evidência da posição sem compartilhar senha ou URLs autenticadas. Confirme também que os cinco canais previamente operantes de outro gravador continuam abrindo no mosaico.
