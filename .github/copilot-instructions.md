# Copilot Instructions - biblioWebapi

## Contexto do projeto
- Backend Django + DRF com organização em camadas DDD:
  - `domain` (entidades/regras)
  - `application` (casos de uso)
  - `infrastructure` (integrações externas)
  - `presentation` (serializers/views/urls)

## Princípios de implementação
- Preferir mudanças incrementais e coesas por responsabilidade.
- Preservar contratos de API existentes; mudanças breaking exigem versionamento/documentação.
- Evitar duplicação de regra de negócio entre camadas.

## Camadas e responsabilidades
- `presentation`: validação de entrada HTTP, status code, serialização.
- `application`: orquestração de caso de uso.
- `domain`: regras de negócio e modelos.
- `infrastructure`: clientes HTTP externos, tradução, mapeamentos e resiliência.

## Integrações externas
- Toda integração externa deve ter:
  - timeout explícito
  - tratamento de erro e fallback
  - logging estruturado em caso de falha
  - mapeamento de resposta para DTO interno estável
- Nunca acoplar response raw externo diretamente ao serializer de saída.
- Sempre identificar app em chamadas que exigirem User-Agent/email.

## Segurança e configuração
- Segredos apenas via variáveis de ambiente (`.env`), nunca hardcoded.
- Adicionar novas variáveis no `settings.py` e documentar no `.env.example`.
- Não expor credenciais em responses/logs.

## API e contrato
- Endpoints novos devem retornar payload consistente e previsível.
- Usar status code adequado (400 entrada inválida, 404 não encontrado, 502/503 integração indisponível quando aplicável).
- Documentar endpoint no schema OpenAPI (drf-spectacular).

## Qualidade
- Criar testes para fluxos principais e de falha de integração.
- Manter mensagens de erro amigáveis para consumo do frontend.
- Evitar side effects em serializers além de persistência necessária.

## Definition of Done (DoD)
- Endpoint funcional com testes de sucesso e falha.
- Timeout/fallback implementados para integrações externas.
- Variáveis de ambiente adicionadas e documentadas.
- Schema/documentação atualizados.
- Sem regressão nos endpoints existentes.