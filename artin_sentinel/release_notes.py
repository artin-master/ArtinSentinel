RELEASE_TITLE = "Live View Resilience & Audio Controls"
RELEASE_NOTES = [
    "O Live View restaura o mosaico ao fechar uma câmera maximizada, limpa tiles ocultos ao recriar a grade e ignora callbacks tardios de sessões fechadas.",
    "Watchdog detecta decoder sem frames; reconexão usa backoff e permanece isolada por canal. Após falhas repetidas, o canal afetado pode pausar e ser retomado manualmente.",
    "Shutdown cancela retries/timers e aguarda a limpeza de workers e processos de mídia; Stop/Close não inicia reconexão posterior.",
    "Áudio de escuta usa curva perceptual: níveis baixos e médios mais utilizáveis, 0% mudo e 100% no máximo normal. Handoff entre canais aguarda a limpeza do player anterior.",
    "Ganho de microfone independente entre 50% e 200%, com 100% preservando o nível original e limitador contra picos; controles mostram percentual, reset e botão Testar.",
    "Talkback continua associado ao canal original, mantém Stop na sessão correta após troca de seleção e limpa captura/transporte tardios. Diagnósticos são sanitizados.",
    "O zoom duplicado foi removido do inspector; zoom no quadrante e capability backend permanecem. Controles de áudio/PTT cabem em painéis estreitos.",
    "IT-Blue continua em DVRIP/Sofia e MiboCam iMX-C em NetSDK. Modos B/C da MiboCam e outras rotas experimentais não são declarados homologados; não há protocolos novos.",
    "Controles Áudio/Microfone foram verificados visualmente; IT-Blue foi usada para vídeo, áudio/talkback e estabilidade, e MiboCam para layout e controles NetSDK/talkback. Hikvision não foi testado fisicamente e permanece pendente.",
    "A investigação de eventos, detecção, luz e sirene da IT-Blue ficou fora desta release.",
    "A suíte automatizada e a verificação de consistência das fontes oficiais de versão acompanham a release.",
]
CHANGELOG_TEXT = """Artin Sentinel 0.2.94 — Live View Resilience & Audio Controls

- O Live View restaura o mosaico ao fechar uma câmera maximizada, limpa tiles ocultos ao recriar a grade e ignora callbacks/processos tardios de canais fechados. Watchdog detecta FFmpeg vivo sem frames; reconexão isolada usa backoff e pode pausar somente o canal afetado após falhas consecutivas.
- Shutdown cancela timers/retries e aguarda a limpeza de players, processos e workers. Stop/Close não provoca reconexão posterior e uma falha não reinicia os demais canais.
- Áudio de escuta usa curva perceptual com níveis baixos/médios mais utilizáveis; 0% continua mudo e 100% mantém o máximo normal. Trocas de canal/Main/Sub aguardam a limpeza do player anterior; rótulo e percentual são exibidos em tempo real.
- Ganho independente do microfone: 50%–200%, 100% preserva o nível original, processamento antes da codificação e limitador contra picos. A interface mostra percentual, reset para 100% e botão “Testar”. Talkback permanece associado ao canal original, Stop controla a sessão correta após troca de seleção e cleanup tardio de captura/transport é aplicado.
- Zoom duplicado removido do inspector; zoom no quadrante e capability do backend permanecem. Controles Áudio/Microfone, seletor NetSDK/PTT e nomes longos cabem em larguras menores.
- IT-Blue continua usando DVRIP/Sofia e MiboCam iMX-C continua usando NetSDK. Modos B/C da MiboCam não são declarados homologados, capacidades podem depender de validação física por modelo e nenhum protocolo novo é anunciado.
- Build de campo usada nos equipamentos disponíveis. Controles Áudio/Microfone conferidos visualmente; IT-Blue usada para vídeo, áudio/talkback e estabilidade; MiboCam usada para layout e controles NetSDK/talkback. Hikvision não foi validado fisicamente por indisponibilidade e permanece pendente.
- A investigação de eventos/detecção/luz/sirene da IT-Blue não faz parte da 0.2.94. A suíte automatizada e a consistência de versão acompanham a release.
"""
