# Política de Segurança do Projeto

## Objetivo
Este documento define uma abordagem segura e orientada para o desenvolvimento e operação do sistema de agendamento de laboratórios.

## Princípios
- Nunca commitar segredos, chaves ou credenciais.
- Usar variáveis de ambiente para configurações sensíveis.
- Manter `DEBUG=False` em produção.
- Atualizar dependências com frequência.
- Aplicar validações fortes nos formulários e no backend.
- Registrar logs e monitorar falhas de autenticação e autorização.

## Checklist de Segurança
1. Criar um `.env` a partir do `.env.example`.
2. Definir `SECRET_KEY` forte para cada ambiente.
3. Ajustar `ALLOWED_HOSTS` e `CSRF_TRUSTED_ORIGINS`.
4. Usar PostgreSQL com credenciais exclusivas.
5. Validar permissões em todas as views relevantes.
6. Escrever testes para regras críticas de negócio.
7. Revisar dependências e vulnerabilidades periodicamente.

## Metodologia Recomendada
- Desenvolvimento orientado por testes (TDD).
- Refatoração incremental de views e lógica de negócio.
- Centralização das regras em serviços ou helpers.
- Separação clara entre configuração, regras de negócio e apresentação.
- Revisão de segurança antes de cada release.
