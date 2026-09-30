# Arquitetura

```text
UI PySide6
   |
Application Services
   |---- Sites / Inventory
   |---- Discovery Engine
   |---- Monitoring Engine
   |---- Diagnostics
   |---- Event History
   |
Provider Registry
   |---- GenericONVIFProvider
   |---- IntelbrasProvider
   |---- HikvisionProvider
   `---- futuros providers
   |
Read-only Protocol Layer
   |---- WS-Discovery / ONVIF
   |---- RTSP
   |---- HTTP/HTTPS
   |---- ICMP/TCP
   `---- SNMP (roadmap)
   |
SQLite
```

## Princípios

1. Equipamento é a entidade principal; IP é atributo mutável.
2. Protocolos abertos primeiro; provider específico apenas quando necessário.
3. Recursos desconhecidos permanecem `unknown`; o sistema não presume saúde.
4. Escrita em equipamentos fica separada e desabilitada por padrão.
5. Compatibilidade é registrada por fabricante, modelo e firmware quando validada.
