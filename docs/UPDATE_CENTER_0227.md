# Artin Sentinel 0.2.27 — Update Center + ArtinUpdates

## Objetivo

A 0.2.27 transforma a fundação de atualização criada nas versões iniciais em um fluxo completo e coordenado, seguindo a mesma arquitetura planejada para os aplicativos Artin: **ArtinUpdates** central, canais Stable/Beta, pacote versionado, SHA-256 obrigatório, instalação somente com consentimento e relançamento após atualização.

A atualização do aplicativo permanece independente da AKDB. A AKDB compartilhada continua podendo evoluir por seu próprio mecanismo/revisão no futuro.

## Fluxo do operador

1. `Configuração → Atualizações` consulta o manifesto do canal selecionado.
2. A verificação de metadados pode ocorrer ao iniciar, respeitando intervalo mínimo de 6 horas.
3. Se houver versão mais nova, o Sentinel mostra versão, título e notas.
4. O download só começa após o operador escolher **Baixar e instalar**.
5. O ZIP é comparado com o SHA-256 do manifesto.
6. Se houver assinatura Ed25519 e chave pública confiável, a assinatura do manifesto também é validada. O canal pode ser configurado para exigir assinatura.
7. O ZIP é extraído em diretório temporário endurecido; path traversal, caminhos absolutos e links simbólicos são bloqueados.
8. O Sentinel pede uma confirmação final.
9. O helper externo é iniciado, a GUI fecha de forma coordenada e libera streams/banco/workers.
10. O helper espera até 10 segundos pelo processo principal. Só depois executa `install.sh`.
11. O instalador existente registra `pending-release-notes.json`, relança o Sentinel e a nova versão mostra **Novidades desta versão** uma única vez.

Não há atualização silenciosa.

## Manifesto ArtinUpdates

O formato usado é `artin-update-manifest-v1`.

Estrutura esperada no serviço/repositório central:

```text
ArtinUpdates/
├── sentinel/
│   ├── stable.json
│   └── beta.json
├── netlens/
│   ├── stable.json
│   └── beta.json
└── rescnow/
    ├── stable.json
    └── beta.json
```

Exemplo mínimo:

```json
{
  "schema": "artin-update-manifest-v1",
  "app_id": "artin-sentinel",
  "channel": "stable",
  "version": "0.2.27",
  "title": "Update Center + ArtinUpdates",
  "notes": ["Centro de Atualizações", "SHA-256 obrigatório"],
  "release_url": "https://github.com/ORG/REPO/releases/tag/v0.2.27",
  "package": {
    "url": "https://github.com/ORG/REPO/releases/download/v0.2.27/ArtinSentinel_0.2.27_update_center.zip",
    "sha256": "<64 hex>",
    "size": 1234567
  }
}
```

A URL base configurada no Sentinel deve apontar para a raiz que contém `sentinel/stable.json` e `sentinel/beta.json`. Também é aceita uma URL direta para um arquivo `.json`.

## Assinatura Ed25519

O updater suporta:

```json
"signature": {
  "key_id": "artin-updates-2026",
  "value": "<assinatura-base64>"
}
```

A assinatura cobre o JSON canônico do manifesto **sem** o bloco `signature`. A chave pública confiável é provisionada localmente em:

```text
~/.local/share/artin-sentinel/trusted-update-keys.json
```

Formato:

```json
{
  "keys": {
    "artin-updates-2026": "<chave-publica-ed25519-raw-base64>"
  }
}
```

A chave privada de publicação nunca deve ser incluída no aplicativo, ZIP, Git ou AKDB.

## Publisher

`tools/build_update_manifest.py` gera um manifesto a partir do ZIP publicado, calculando SHA-256 e tamanho. Opcionalmente ele assina o manifesto quando recebe uma chave privada Ed25519 por arquivo ou variável de ambiente.

## Persistência e segurança

A atualização substitui somente o pacote/runtime. Permanecem fora da árvore de instalação:

- `~/.local/share/artin-sentinel/sentinel.db`;
- Sites e layouts;
- relatórios e logs;
- AKDB compartilhada;
- credenciais no keyring;
- configurações de atualização.

Pacotes com hash incorreto nunca chegam ao instalador.
