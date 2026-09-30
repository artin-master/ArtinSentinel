# Piloto de gravadores externos — 0.2.49

## Teste operacional

1. Garanta uma rota privada ativa entre a estação Sentinel e a rede do outro local (VPN já configurada fora do Sentinel). Teste o IP ou nome do DVR a partir desta estação.
2. No Sentinel, crie ou selecione o Site do outro local. Em **Equipamentos → Adicionar**, escolha **Outro local • rede privada/VPN**, defina DVR/NVR/XVR, escolha o protocolo Intelbras/Dahua ou Hikvision/JFL se souber a família e informe o IP/host alcançável. Não digite número de série/cloud no campo IP.
3. Selecione o equipamento e execute **Diagnosticar**. Um ping sem resposta não prova que o DVR está offline; observe as portas acessíveis e o resultado RTSP.
4. Execute **Canais / Testar stream**, informe a credencial do próprio DVR e valide a leitura. Se o protocolo ainda for genérico, use **Editar identificação** para escolhê-lo. A senha fica na sessão ou no cofre seguro se o operador optar por salvar.
5. Abra um canal disponível em Ao vivo, prefira substream e verifique reconexão ao interromper/restaurar a rede privada.

O cadastro não ativa VPN nem abre portas no roteador; ele classifica um endereço já alcançável. As URLs Web/RTSP opcionais devem ser fornecidas sem usuário ou senha embutidos. O acesso por código de série em Intelbras Cloud, Hik-Connect ou outras plataformas requer integração específica de cada fabricante. Esta etapa não implementa login nessas plataformas.

## Critério para o primeiro DVR externo

Registrar fabricante, modelo, firmware, número de canais, caminho atual de acesso remoto (VPN ou aplicativo cloud) e qual computador está executando o Sentinel. Não incluir senhas, números de série completos ou links autenticados no relato de testes. Confirmar diagnóstico, canais inventariados, imagem ao vivo e estabilidade após reconexão.
