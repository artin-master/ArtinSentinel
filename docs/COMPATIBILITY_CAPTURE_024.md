# Compatibility Capture — 0.2.4

A 0.2.4 adiciona um fluxo de campo para testar mais modelos sem transformar observações isoladas em regras permanentes automaticamente.

## Fluxo

1. Descobrir/adicionar o equipamento.
2. Corrigir a identidade manualmente se necessário.
3. Executar diagnóstico e, quando for gravador, leitura de canais.
4. Em **Configuração → Equipamentos**, usar **Exportar perfil AKDB**.
5. Revisar o JSON e anexá-lo ao ciclo de validação do modelo.

## Privacidade

O relatório não inclui senha, token, MAC, serial, IP real nem credenciais embutidas em URLs. Caminhos RTSP são preservados com o host substituído por `<device>` para que a compatibilidade técnica possa ser estudada.

## Estados de conhecimento

Uma captura não promove um perfil automaticamente. O fluxo continua distinguindo `detected`, `tested`, `field-detected` e `field-validated`.
