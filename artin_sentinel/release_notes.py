RELEASE_TITLE = "PTZ, Stream Diagnostics & Channel Health"
RELEASE_NOTES = [
    "PTZ exige capability/provider comprovados; Stop conserva alvo, direção e velocidade originais, e os controles encerram o movimento com segurança ao trocar ou fechar a seleção.",
    "O diagnóstico Main/Sub informa codecs, resolução, faixas de áudio e causas distintas, com cancelamento sem persistir resultados parciais.",
    "A saúde por canal reduz alertas repetidos e informa RECUPERADO na primeira confirmação saudável após uma falha.",
    "Talkback centraliza a prontidão das rotas existentes DVRIP/Sofia, Intelbras HTTP postAudio e NetSDK, com diagnósticos sanitizados.",
    "A validação física relatada cobriu o MHDX 1004 e câmeras IP disponíveis; Hikvision não foi testado fisicamente e permanece pendente.",
    "A suíte automatizada e a verificação de consistência da versão acompanham a release.",
]
CHANGELOG_TEXT = """Artin Sentinel 0.2.93 — PTZ, Stream Diagnostics & Channel Health

- PTZ exige capability/provider comprovados, reduz inferências genéricas e envia Stop ao alvo original com direção e velocidade capturadas. Resultados atrasados não são associados ao equipamento selecionado depois.
- O diagnóstico das rotas Main/Sub cadastradas informa codec e resolução de vídeo, presença/ausência de áudio e, quando disponível, codec, taxa e canais. Distingue autenticação, stream ausente, timeout, RTSP indisponível e decoder incompatível; cancelar não persiste resultado parcial.
- A saúde por canal evita alertas repetidos durante a mesma falha, trata transições SEM SINAL/OFFLINE e apresenta RECUPERADO na primeira confirmação saudável, preservando o histórico.
- Talkback centraliza a readiness das rotas existentes DVRIP/Sofia, Intelbras HTTP postAudio e Intelbras NetSDK. Mensagens identificam falta de FFmpeg, microfone, credencial ou runtime, e diagnósticos sanitizam credenciais conhecidas.
- A validação física informada cobriu o MHDX 1004 e câmeras IP/MiboCam disponíveis, sem problemas aparentes nos fluxos disponíveis. Hikvision não foi validado fisicamente por indisponibilidade do equipamento e permanece pendente.
- Não se declara compatibilidade nova: ONVIF genérico não habilita PTZ automaticamente e equipamentos atrás de gravadores não recebem talkback por inferência.
- A suíte automatizada e a verificação das fontes oficiais de versão acompanham a release.
"""
