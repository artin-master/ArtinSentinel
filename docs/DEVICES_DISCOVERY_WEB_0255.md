# Equipamentos: descoberta e acesso Web (0.2.55)

1. Acesse **Configuração → Equipamentos** e selecione o Site. Clique em **Buscar / atualizar**. Resultados novos aparecem acima dos equipamentos cadastrados.
2. Selecione um resultado para consultar a evidência, abrir **Detalhes da busca** ou exportar o **Relatório AKDB**. A inclusão usa **Adicionar selecionado** ou duplo clique.
3. **Web do encontrado** abre a URL HTTP/HTTPS identificada pela busca no navegador padrão, desde que a URL corresponda ao IP encontrado e não contenha usuário nem senha. O botão fica desabilitado na ausência de URL válida. O botão **Web** já existente atende equipamentos cadastrados.
4. Se a página pedir autenticação, informe os dados somente no navegador. Uma porta HTTP/HTTPS detectada não confirma que a configuração Web está disponível. A busca é local; dispositivos remotos somente por Cloud não aparecem por esse método.

Validação visual e teste de autenticação dependem de computador com PySide6 e equipamentos reais. Nenhuma credencial é acrescentada à URL pelo botão novo.
