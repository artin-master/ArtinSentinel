# AKDB Safe Apply — 0.2.44

A atualização oficial usa uma transação SQLite para inserir identidades e extensões e registrar a revisão. Qualquer exceção reverte toda a operação. A fila de candidatos e as evidências locais ficam separadas.

Revisões anteriores à instalada, reutilização do mesmo número com hash diferente e conflitos de mesma revisão são bloqueados. O Sentinel mostra o motivo em Configuração → AKDB, sem afirmar que a base foi sincronizada. Uma revisão posterior válida pode ser avaliada novamente.

O digest SHA-256 detecta alteração do bundle em relação ao manifesto recuperado, mas o manifesto 0.2.43/0.2.44 ainda não possui assinatura criptográfica própria. A autenticação da fonte depende de HTTPS e do endereço configurado. A publicação oficial assinada fica para um próximo ciclo, depois do provisionamento de uma chave pública confiável no aplicativo.
