# 0.1.4 — VMS Workspace

## Objetivo

Separar claramente a experiência de **operação de CFTV** da experiência de **configuração/manutenção técnica**.

Até a 0.1.3, o Sentinel abria em uma interface administrativa com tabelas. A 0.1.4 torna o Ao vivo o centro da aplicação.

## Estrutura da interface

```text
Artin Sentinel | Ao vivo | Reprodução | Eventos | Saúde | Configuração
-----------------------------------------------------------------------
Sites / fontes        Mosaico de vídeo                    Status
- Site Local          [ CAM 01 ][ CAM 02 ]                Online/offline
  - DVR               [ CAM 03 ][ CAM 04 ]                Seleção
    - Canal 01                                            Atividade
    - Canal 02
```

### Operação diária

- Ao vivo
- Reprodução
- Eventos
- Saúde

### Manutenção

- Sites
- Equipamentos
- Descoberta
- Diagnóstico
- Leitura de canais

## Mosaico

Layouts disponíveis nesta fundação:

- 1 janela;
- 4 janelas;
- 9 janelas;
- 16 janelas.

O usuário seleciona uma janela e dá duplo clique em uma fonte da árvore para associá-la ao mosaico.

Nesta versão a associação é visual/lógica. Não há decodificação de vídeo até a validação do provider RTSP.

## Identidade do gravador

`xvr` continua podendo existir internamente como classificação técnica, mas não é um rótulo adequado ao operador. Na interface é exibido como **DVR / Multi HD**.

O modelo não é inferido a partir de portas genéricas. Quando não existe evidência confiável, o Sentinel mostra `—`. O operador pode usar **Editar identificação** para registrar o modelo conhecido, por exemplo `MHDX 1004`.

## Segurança

Nenhuma função de escrita foi adicionada. O workspace não altera configurações, gravações, canais ou credenciais nos equipamentos.
