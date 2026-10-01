# Teste de campo — Artin Sentinel 0.2.36

## Objetivo principal

Confirmar quais equipamentos do ambiente realmente implementam a HTTP API Intelbras e quais capacidades de áudio o próprio firmware anuncia.

## MHDX 1004

1. Configuração → Equipamentos → selecione o MHDX 1004.
2. Garanta que a credencial esteja disponível no Sentinel.
3. Abra `Mais ▾` → `Testar API Intelbras (somente leitura)`.
4. Registrar o resultado: versão, áudio IN, áudio OUT e estado `postAudio candidato`.
5. Confirmar que vídeo CAM 1–5 e áudio CAM 5 continuam normais.

## Mibo iMX C

1. Selecione a iMX C cadastrada diretamente.
2. Execute o mesmo probe.
3. Registrar se a API responde ou se as CGIs não estão disponíveis.
4. Confirmar que vídeo e áudio de escuta continuam normais e que MIC não é habilitado automaticamente.

## Segurança esperada

- Nenhum áudio transmitido.
- Nenhuma configuração alterada.
- Nenhuma senha/token exposto no resultado.
- Falha 401/403 deve ser tratada como autenticação recusada, não como ausência da API.
