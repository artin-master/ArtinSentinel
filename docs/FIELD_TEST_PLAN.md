# Plano de teste de campo — 0.1.7

## Intelbras MHDX 1004 — 192.168.15.254

1. Confirmar que o equipamento continua como **DVR / Multi HD**.
2. Em **Ler canais do gravador**, definir um nome amigável, por exemplo **DVR Casa**.
3. Confirmar leitura dos quatro canais já validados na 0.1.6.
4. Se o cofre seguro estiver disponível, marcar **Salvar credencial com segurança**.
5. Abrir **Ao vivo** e colocar os quatro canais no mosaico.
6. Confirmar imagem simultânea em 4 câmeras sem congelar a GUI.
7. Em um canal, testar **Substream**.
8. No mesmo canal, testar **Main stream**.
9. Voltar para **Automático** e confirmar:
   - mosaico 4 câmeras → substream;
   - visualização única → main stream.
10. Renomear um canal, por exemplo **Portão**, e confirmar persistência após reiniciar o app.
11. Fechar e reabrir o Sentinel:
   - nome **DVR Casa** deve permanecer;
   - aliases dos canais devem permanecer;
   - preferências de stream devem permanecer;
   - se a credencial foi salva, Live View deve conseguir reconectar sem nova digitação.
12. Usar **Esquecer credencial** e confirmar que o Sentinel volta a solicitar senha para o vídeo.

## Estabilidade

- alternar entre mosaicos 1/4/9/16;
- limpar mosaico enquanto streams estão ativos;
- fechar o Sentinel com quatro streams ativos;
- desconectar/reconectar rede ou DVR e observar reconexão automática;
- confirmar ausência de SIGSEGV/coredump no fluxo de credencial e vídeo.

## Outros equipamentos da rede

- Intelbras Mibo Cam: continuar descoberta/fingerprint e levantamento de RTSP/ONVIF.
- IT-Blue: continuar descoberta genérica por serviços/ONVIF/RTSP.
