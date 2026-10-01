# Providers

A interface `DeviceProvider` normaliza identificação e recursos específicos de fabricantes.

Providers iniciais:

- `GenericONVIFProvider`: fallback para equipamentos ONVIF/genéricos.
- `IntelbrasProvider`: fundação para identificação Intelbras; sem APIs proprietárias nesta build.
- `HikvisionProvider`: fundação para identificação Hikvision; sem OpenAPI/Hik-Connect nesta build.

JFL, Haiz, Positivo e Aiktek entram inicialmente pela camada genérica e receberão providers conforme testes físicos/documentação.
