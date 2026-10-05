RELEASE_TITLE = "Menu Selection UX"
RELEASE_NOTES = [
    "Menus e submenus destacam com clareza a opção sob o cursor, reduzindo cliques equivocados.",
    "Itens marcados/checked mantêm estado visual próprio, diferente do hover e do foco.",
    "Listas suspensas de QComboBox usam o mesmo padrão visual para hover, seleção e itens desabilitados.",
    "A alteração é somente de UX/estilo e não modifica vídeo, áudio, PTZ, descoberta, protocolos ou persistência.",
]
CHANGELOG_TEXT = """Artin Sentinel 0.2.94.1 — Menu Selection UX

- O Live View restaura o mosaico ao fechar uma câmera maximizada, limpa tiles ocultos ao recriar a grade e ignora callbacks/processos tardios de canais fechados. Watchdog detecta FFmpeg vivo sem frames; reconexão isolada usa backoff e pode pausar somente o canal afetado após falhas consecutivas.
- Shutdown cancela timers/retries e aguarda a limpeza de players, processos e workers. Stop/Close não provoca reconexão posterior e uma falha não reinicia os demais canais.
- Áudio de escuta usa curva perceptual com níveis baixos/médios mais utilizáveis; 0% continua mudo e 100% mantém o máximo normal. Trocas de canal/Main/Sub aguardam a limpeza do player anterior; rótulo e percentual são exibidos em tempo real.
- Ganho independente do microfone: 50%–200%, 100% preserva o nível original, processamento antes da codificação e limitador contra picos. A interface mostra percentual, reset para 100% e botão “Testar”. Talkback permanece associado ao canal original, Stop controla a sessão correta após troca de seleção e cleanup tardio de captura/transport é aplicado.
- Zoom duplicado removido do inspector; zoom no quadrante e capability do backend permanecem. Controles Áudio/Microfone, seletor NetSDK/PTT e nomes longos cabem em larguras menores.
- IT-Blue continua usando DVRIP/Sofia e MiboCam iMX-C continua usando NetSDK. Modos B/C da MiboCam não são declarados homologados, capacidades podem depender de validação física por modelo e nenhum protocolo novo é anunciado.
- Build de campo usada nos equipamentos disponíveis. Controles Áudio/Microfone conferidos visualmente; IT-Blue usada para vídeo, áudio/talkback e estabilidade; MiboCam usada para layout e controles NetSDK/talkback. Hikvision não foi validado fisicamente por indisponibilidade e permanece pendente.
- A investigação de eventos/detecção/luz/sirene da IT-Blue não faz parte da 0.2.94.1. A suíte automatizada e a consistência de versão acompanham a release.
"""
