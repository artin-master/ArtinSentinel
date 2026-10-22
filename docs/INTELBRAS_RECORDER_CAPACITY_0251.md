# Piloto 0.2.51: capacidade de canais Intelbras

## Evidência recebida

| Modelo | Capacidade mostrada no próprio gravador | Evidência de stream recebida |
| --- | ---: | --- |
| MHDX 1004 | 4 canais analógicos + 1 IP, conforme teste anterior | teste local anterior |
| NVD 1416 | 16 canais | no Sentinel 0.2.41: 5 posições, 0 com mídia validada |
| NVD 1516 | 16 canais | ainda não enviada |
| MHDX 1216 | 16 canais | ainda não enviada |

O 0.2.41 confundia um dispositivo Intelbras sem modelo identificado com o perfil MHDX 1004, limitando toda a busca a cinco posições. O perfil de cinco canais agora exige evidência do modelo 1004. Os demais três modelos têm identidade separada no Core r13 e capacidade candidata de 16 posições na extensão Sentinel da AKDB, com base nas telas do próprio equipamento. O tipo e a combinação de entradas analógicas/IP do MHDX 1216, a URL RTSP, o áudio e a saúde real de cada posição ainda precisam de validação física. Nos NVDs os canais são classificados como IP; em modelos genéricos o tipo permanece desconhecido até haver evidência.

## Teste de campo

1. Instale a 0.2.51 com `./install.sh` no computador Fedora/Ubuntu que executa o Sentinel. O instalador detecta e oferece instalar pacotes normais do sistema, cria o ambiente Python e instala as dependências do aplicativo. `./install.sh --check` apenas diagnostica. A SDK Intelbras é importada separadamente em **Configuração → Atualizações** quando necessária.
2. No Site com NVD 1416, NVD 1516 ou MHDX 1216, escolha o gravador, abra **Editar identificação** e informe o modelo exato se ainda constar apenas “Intelbras”. Preserve o tipo DVR/NVR/XVR conforme o equipamento.
3. Abra **Canais / Testar stream**. Em **Canais a verificar**, escolha **16** para esses modelos; no MHDX 1004, escolha **5**. O valor fica salvo apenas naquele gravador e pode ser ajustado em nova leitura; modelos ainda desconhecidos começam em 16 para Intelbras, mas o operador deve conferir a capacidade na interface do equipamento.
4. Confira quantas **posições foram verificadas** e quantas tiveram **mídia validada**. Posição listada não significa vídeo ativo. Compare cenas dos canais de vídeo confirmados, especialmente quando várias rotas podem repetir a mesma câmera. Se o resultado continuar com zero mídia, exporte o perfil AKDB sanitizado e a evidência da coluna de diagnóstico para investigação de autenticação, RTSP/ONVIF ou rota de vídeo; não envie senha, serial, MAC ou URL com credenciais.

**Limite técnico:** o fluxo Intelbras desta versão ainda testa URLs Dahua/Intelbras candidatas. Com capacidade de 16, o scanner pode levar mais tempo do que com cinco posições. O resultado de zero vídeo da 0.2.41 não permite afirmar a causa nem assegurar Live View para os NVDs antes de teste de campo.
