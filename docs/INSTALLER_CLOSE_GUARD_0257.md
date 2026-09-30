# Guard de processo durante instalação (0.2.57)

- O instalador identifica processos do usuário atual executando o entrypoint instalado `artin-sentinel` ou `python -m artin_sentinel.app`. Faz a primeira verificação depois de validar a versão e antes de instalar pacotes do sistema; repete a verificação imediatamente antes de mexer no runtime Python.
- Com terminal interativo, informa os PIDs e solicita que o operador feche todas as janelas. **Enter** verifica novamente; **C** cancela. Nenhum processo é encerrado à força.
- Sem terminal, a instalação aborta com código 3 e mensagem de fechamento, inclusive com `--yes`. O diagnóstico `--check` não modifica dados e continua funcionando com o aplicativo aberto.
- O atualizador interno fecha a própria GUI depois de validar o pacote, aguarda o processo terminar e então chama o instalador. Se outra instância ainda estiver aberta, o instalador aborta e registra a mensagem no log de atualização; não substitui arquivos com o app ativo.
- Após uma atualização validada, o relançamento usa a mesma detecção de processos, evitando abrir uma cópia duplicada.

O nome do processo é confrontado com os argumentos reais do usuário em `/proc`; não é feita busca ampla por substring de nome, que poderia confundir o próprio instalador com o aplicativo.
