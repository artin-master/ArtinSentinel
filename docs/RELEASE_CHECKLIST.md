# Checklist permanente de fechamento oficial

Durante um ciclo de desenvolvimento, manter a versão oficial anterior e não
publicar, criar tag ou fazer push sem a autorização de fechamento correspondente.
Este documento é procedimento futuro; sua criação não autoriza nem executa release.

Para fechar oficialmente a 0.2.95 (e aplicar o mesmo fluxo às releases seguintes):

1. Atualizar de forma consistente as fontes oficiais de versão, release notes,
   changelog ativo, README e expectativas da versão corrente nos testes.
   Preservar documentação histórica e pendências físicas por modelo, incluindo
   Hikvision enquanto não houver equipamento/resultado comprovado.
2. Executar `git diff --check`, testes de versão e testes relacionados; executar
   a suíte completa. Não prosseguir com falhas, erros ou skips inesperados.
3. Criar o commit oficial `release: Artin Sentinel 0.2.95`, preservando os commits
   funcionais anteriores sem squash automático.
4. Gerar o ZIP oficial a partir desse commit e validar CRC/estrutura, wheel,
   versão interna, compileall, scripts, consistência de versão e SHA-256.
5. Confirmar working tree limpo e HEAD exatamente no commit oficial.
6. Conferir `origin` e refs remotas de `main` e `release/0.2.95`. Se a branch
   de release já apontar para outro commit, parar; não sobrescrever histórico.
7. Com autorização de publicação do commit, disponibilizá-lo somente na branch
   separada, sem force:

   ```bash
   git push origin HEAD:refs/heads/release/0.2.95
   ```

8. Confirmar com `git ls-remote` que `refs/heads/release/0.2.95` aponta exatamente
   para o commit oficial e que `main` permanece no hash conferido antes do push.
9. Não alterar `main`, não fazer merge automático e não usar force push.
10. Somente após essa confirmação, abrir/validar o pacote no Artin Publisher.
    Tag e release no GitHub exigem instrução explícita separada.
