# Política de Segurança do Projeto

## Objetivo

Definir as práticas de segurança adotadas no desenvolvimento e na operação do
sistema de agendamento de laboratórios, e registrar o que já está aplicado no
código.

## Princípios

- Nunca commitar segredos, chaves ou credenciais.
- Usar variáveis de ambiente para configurações sensíveis.
- Manter `DEBUG=False` em produção.
- Toda operação que altera estado acontece via `POST` com token CSRF.
- Toda entrada vinda do cliente é validada contra a lista de valores aceitos.
- Atualizar dependências com frequência.
- Registrar logs e monitorar falhas de autenticação e autorização.

## Controles implementados

| Controle | Onde |
| :-- | :-- |
| `SECRET_KEY` obrigatória em produção (a aplicação não sobe com a chave de exemplo) | `setup/settings.py` |
| `ALLOWED_HOSTS` não aceita `*` com `DEBUG=False` | `setup/settings.py` |
| Cookies de sessão e CSRF com `HttpOnly`, `Secure` e `SameSite=Lax` | `setup/settings.py` |
| Sessão expira em 8h e ao fechar o navegador (máquinas compartilhadas) | `setup/settings.py` |
| HSTS, `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy` | `setup/settings.py` |
| Ações destrutivas exigem `POST` + CSRF (`@require_POST`) | `agendamentos/views.py` |
| Papéis centralizados em decoradores, sem checagem duplicada por view | `agendamentos/decorators.py` |
| Contas não aprovadas bloqueadas em todas as telas de uso | `agendamentos/decorators.py` |
| Status e tipos de perfil validados contra `*_CHOICES` | `agendamentos/views.py` |
| Administrador não consegue se rebaixar nem se excluir (anti-lockout) | `agendamentos/views.py` |
| Reserva criada sob `select_for_update` (evita corrida de sobreposição) | `agendamentos/views.py` |
| `.env` fora da imagem Docker | `.dockerignore` |

## Checklist de implantação

1. Criar um `.env` a partir do `.env.example`.
2. Definir `SECRET_KEY` forte e exclusiva do ambiente.
3. Definir `DEBUG=False`.
4. Ajustar `ALLOWED_HOSTS` e `CSRF_TRUSTED_ORIGINS` para o domínio real.
5. Usar PostgreSQL com usuário e senha exclusivos da aplicação.
6. Servir atrás de proxy reverso com TLS (`SECURE_SSL_REDIRECT` ativo).
7. Trocar `runserver` por `gunicorn` e servir estáticos por WhiteNoise/Nginx.
8. Rodar `python manage.py test` e `python manage.py check --deploy` antes do release.

## Pendências conhecidas

Itens identificados e ainda **não** implementados:

- **Sem limite de tentativas de login.** Não há proteção contra força bruta na
  tela de autenticação. Recomenda-se `django-axes` ou limitação no proxy reverso.
- **Enumeração de e-mail no cadastro.** A mensagem "este e-mail já está
  cadastrado" confirma a existência de uma conta. É um requisito funcional da
  tela, mas vale avaliar a troca por confirmação por e-mail.
- **Sem registro de auditoria.** Cancelamentos e mudanças de permissão gravam
  autor e data no próprio registro, mas não há trilha de auditoria completa.
- **`runserver` no `docker-compose.yml`.** Adequado para desenvolvimento; a
  implantação real exige `gunicorn`.

## Proteção de dados pessoais (LGPD)

O sistema armazena nome, e-mail e matrícula dos usuários, além do histórico de
uso das máquinas. Recomendações:

- Não inserir dados sensíveis (art. 5º, II da LGPD) em campos livres como
  observações e justificativas.
- Restringir o perfil `ADMIN` ao mínimo necessário — é o único que enxerga
  e-mails e o histórico completo de reservas de terceiros.
- Definir e aplicar um prazo de retenção para os agendamentos antigos.

## Metodologia

- Desenvolvimento orientado por testes, com teste de regressão para cada falha corrigida.
- Refatoração incremental de views e lógica de negócio.
- Centralização das regras em helpers e decoradores.
- Revisão de segurança antes de cada release.
