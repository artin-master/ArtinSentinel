# Artin Sentinel 0.2.94 — Live View Resilience & Audio Controls

- **Live View:** fechar uma câmera maximizada restaura o mosaico e recriar a grade limpa também os tiles ocultos. Callbacks atrasados e sessões canceladas não reabrem canais fechados. Watchdog detecta decoder ativo sem frames e recupera somente o canal afetado, com backoff e pausa retomável após falhas repetidas.
- Encerrar o aplicativo cancela retries/timers e aguarda a limpeza de workers, players e processos de mídia. Uma falha em um canal não reinicia os demais.
- **Áudio de escuta:** curva perceptual torna níveis baixos e médios mais utilizáveis; 0% permanece mudo e 100% mantém o máximo normal. Trocas de canal/Main/Sub aguardam a limpeza do player anterior, e a interface mostra rótulo e percentual atualizados.
- **Microfone/talkback:** ganho independente ajustável entre 50% e 200%; 100% preserva o nível original e o limitador protege contra picos antes da codificação. O percentual, reset para 100% e botão “Testar” ficam visíveis. Stop continua associado à sessão/canal original após trocar a seleção; diagnósticos permanecem sanitizados.
- **UX:** removido o zoom duplicado do inspector; o zoom no quadrante e a capability do backend foram preservados. As linhas Áudio/Microfone se adaptam a larguras menores; seletor NetSDK e nomes longos permanecem dentro do painel.
- IT-Blue continua no caminho DVRIP/Sofia; MiboCam iMX-C continua no NetSDK. Os modos B/C da MiboCam não são declarados homologados e não foram anunciados protocolos novos. Capacidades podem depender de validação física por modelo.
- **Validação de campo:** controles Áudio/Microfone foram conferidos visualmente; IT-Blue foi usada em vídeo, áudio/talkback e estabilidade; MiboCam foi usada no layout e controles NetSDK/talkback. Hikvision não foi validado fisicamente por indisponibilidade do equipamento e continua pendente. A investigação de eventos/detecção/luz/sirene da IT-Blue não faz parte desta versão.
- A suíte automatizada e a consistência entre as fontes de versão acompanham a release.

# Artin Sentinel 0.2.93 — PTZ, Stream Diagnostics & Channel Health

- PTZ usa capabilities e providers comprovados, evita inferências genéricas, preserva alvo, direção e velocidade originais para Stop, encerra o movimento ao trocar/fechar a seleção e descarta resultados atrasados associados a outra seleção.
- Diagnóstico Main/Sub cobre somente rotas cadastradas e informa codec/resolução de vídeo, faixas de áudio disponíveis e causas distintas de falha. Cancelamento não persiste resultados parciais.
- Saúde por canal reduz alertas repetidos, trata transições SEM SINAL/OFFLINE e sinaliza RECUPERADO na primeira confirmação saudável, preservando o histórico.
- Talkback consolida prontidão das rotas existentes DVRIP/Sofia, Intelbras HTTP postAudio e Intelbras NetSDK, com mensagens de dependências ausentes e sanitização de credenciais conhecidas.
- Validação física informada: MHDX 1004 e câmeras IP/MiboCam disponíveis foram usados, sem problemas aparentes nos fluxos verificados. Hikvision não foi validado fisicamente por indisponibilidade do equipamento; a validação específica permanece pendente.
- ONVIF genérico não habilita PTZ automaticamente; equipamentos atrás de gravadores não recebem capability de talkback por inferência. Não são anunciados protocolos ou compatibilidades novos.

# Artin Sentinel 0.2.92 — Acesso Web confirmado e gestão de equipamentos

- A descoberta sonda HTTP e HTTPS separadamente e registra confirmação e histórico de falhas por endpoint. Porta TCP aberta e `web_url` legado continuam sendo apenas pistas.
- O acesso Web só fica disponível quando há confirmação HTTP. Vários serviços podem ser selecionados; HTTPS confirmado tem preferência e o endereço aberto contém apenas IP, esquema e porta, sem credenciais.
- A tela Configuração → Equipamentos separa cadastrados e descobertos, aproxima as ações da tabela correspondente e agrupa Canais e Excluir da descoberta em Mais.
- O cadastro manual mantém os valores e o diálogo aberto quando a validação falha; o contador da tabela mostra os resultados visíveis em relação ao total.
- A suíte automatizada cobre armazenamento, probe e integração Qt; as três fontes oficiais de versão são verificadas quanto à consistência.

# Artin Sentinel 0.2.91 — Configuração e descoberta

A aba Atualizações permite rolar verticalmente sem esmagar os campos. Equipamentos cadastrados continuam visíveis após a inclusão e após nova busca, com a marca * Incluído. Selecione a linha para ler Canais ou Excluir com a confirmação existente. Ver incluído seleciona o cadastro anterior. Equipamentos arquivados permanecem identificados para restauração.
