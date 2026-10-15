# Artin Sentinel 0.2.95 — Hikvision Playback/Export Hardening

## Objetivo

Esta candidata parte diretamente da 0.2.94.1 e mantém a frente Intelbras/NetSDK 0.3.0 separada. O objetivo imediato é permitir validar, em equipamento Hikvision autorizado, a busca de gravações por canal/período, reprodução do trecho retornado pelo próprio DVR/NVR e exportação MP4 já existentes no Sentinel.

## Correção principal

O fluxo ISAPI existente usa `POST /ISAPI/ContentMgmt/search`. A documentação Hikvision trata `searchID` como identidade da sessão de busca e `searchResultPostion` como cursor de paginação. A implementação anterior gerava um novo searchID a cada página; firmwares antigos podem interpretar isso como uma nova busca.

A 0.2.95 mantém um único searchID por consulta e avança apenas a posição 0/40/80, com limite de 120 resultados por canal e proteção contra página repetida.

## Hardening

- autenticação HTTP 401/403 e ausência do endpoint 404 recebem estados distintos e sanitizados;
- resultados repetidos não são publicados duas vezes;
- URIs RTSP retornadas pelo equipamento são aceitas apenas para o track solicitado e sem credencial embutida;
- o host retornado pelo DVR nunca substitui o endpoint cadastrado: a reprodução/exportação é reroteada para o gravador selecionado;
- o tamanho informado no playbackURI é preservado quando válido;
- a busca multicanal agrega ignored/warnings sem expor usuário, senha, host autenticado ou URL com credencial;
- Intelbras, ONVIF genérico e demais providers não tiveram sua lógica de busca/exportação alterada.

## Estado de validação

A base 0.2.94.1 já continha:
- inventário Hikvision por ISAPI;
- busca de gravações por `/ISAPI/ContentMgmt/search`;
- uso do `playbackURI` retornado pelo equipamento;
- reprodução RTSP do trecho;
- exportação local MP4 via FFmpeg.

A 0.2.95 endurece esse caminho. A correção ainda precisa de validação física no DVR/NVR Hikvision do operador antes de virar release estável. Nenhuma compatibilidade além do cenário testado deve ser anunciada automaticamente.
