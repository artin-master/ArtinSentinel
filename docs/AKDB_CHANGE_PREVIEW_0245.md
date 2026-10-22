# AKDB Change Preview — 0.2.45

Após "Verificar AKDB", o botão "Ver alterações" abre uma prévia somente leitura. Cada entrada informa identidade ou extensão, inclusão/edição/conflito, revisão local e remota e nomes dos campos alterados. Os valores do payload e as evidências locais não são mostrados.

Uma divergência de conteúdo ou de schema na mesma revisão de extensão é um conflito. Nessa situação a prévia continua disponível, mas "Atualizar base" permanece bloqueado. A prévia não envia candidatos nem altera o banco SQLite.

A fonte oficial atual utiliza HTTPS e SHA-256 do bundle. Assinatura própria do manifesto depende de uma chave pública confiável provisionada no Sentinel e segue pendente.
