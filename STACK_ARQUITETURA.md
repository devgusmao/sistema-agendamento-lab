# 📐 Stack e Arquitetura Inicial

> Documento de apoio à decisão sobre a stack e arquitetura do **Sistema de
> Agendamento para Laboratórios de Informática**. Arquivo solto na raiz do
> projeto de propósito — é um rascunho de referência, pode ser apagado quando
> não for mais necessário.

Cada item segue o formato:

**Escolha → Alternativa(s) consideradas → Justificativa**

---

# 🧱 Parte 1 — Stack (tecnologias)

## 1. Linguagem

- **Escolha:** Python 3.11
- **Alternativa(s):** Node.js (JavaScript/TypeScript), Java, PHP
- **Justificativa:** curva de aprendizado baixa para a equipe, grande
  ecossistema para web (Django), produtividade alta para um sistema
  CRUD-heavy (cadastro, agendamento, permissões), e boa integração com
  PostgreSQL via `psycopg2`.

## 2. Framework (Back-end)

- **Escolha:** Django 4.2
- **Alternativa(s):** Flask, FastAPI
- **Justificativa:** Django é "baterias inclusas" — ORM, sistema de
  autenticação, painel administrativo (`/admin`) e proteção contra CSRF/SQL
  Injection prontos de fábrica. Isso acelera a entrega de um sistema com
  múltiplos perfis de acesso (Aluno, Técnico, Administrador, Superusuário)
  sem precisar montar essa infraestrutura do zero, como seria necessário com
  Flask/FastAPI.

## 3. Front-end

- **Escolha:** Server-Side Rendering com Django Templates + CSS puro +
  Flatpickr (JS para seleção de data/hora)
- **Alternativa(s):** SPA com React ou Vue consumindo uma API REST
- **Justificativa:** equipe pequena e sistema com fluxos majoritariamente de
  formulário/CRUD, sem necessidade de interatividade complexa no cliente.
  Renderizar no servidor evita manter uma API separada, elimina etapa de
  build de front-end e reduz a superfície de configuração/deploy — trade-off
  aceito: menor riqueza de interação em troca de simplicidade e velocidade
  de entrega.

## 4. Banco de Dados

- **Escolha:** PostgreSQL 15
- **Alternativa(s):** MySQL, SQLite
- **Justificativa:** suporte robusto a transações e locks (`select_for_update`
  é usado para travar horários sobrepostos e evitar overbooking de
  computadores), open-source, maduro, e com ótima integração com o ORM do
  Django. SQLite foi descartado por não ser adequado a acesso concorrente em
  produção.

## 5. Integrações

- **Escolha:** Flatpickr (seleção de data/hora no front-end), Gunicorn
  (servidor WSGI de produção), `python-decouple` (variáveis de ambiente)
- **Alternativa(s):** bibliotecas nativas de `<input type="datetime-local">`,
  uWSGI, `django-environ`
- **Justificativa:** Flatpickr oferece UX de calendário sem exigir um
  framework JS completo; Gunicorn é o padrão de mercado para servir Django
  em produção com múltiplos workers; `python-decouple` mantém segredos fora
  do código-fonte de forma simples, sem dependências pesadas.

> Não há integrações externas (pagamento, e-mail, APIs de terceiros) nesta
> fase do projeto.

---

# 🏛️ Parte 2 — Arquitetura (organização e deploy)

## 6. Estilo Arquitetural

- **Escolha:** Monólito modular (Django "apps") em container único
- **Alternativa(s):** Microsserviços, arquitetura em camadas com API
  separada do front-end
- **Justificativa:** escopo e equipe atuais não justificam a complexidade
  operacional de microsserviços (orquestração, comunicação entre serviços,
  observabilidade distribuída). Um monólito modular, organizado por app
  Django (`agendamentos`), mantém coesão do domínio e é mais rápido de
  evoluir e implantar nesta fase do projeto.

## 7. Infraestrutura / Deploy

- **Escolha:** Docker + Docker Compose (serviços `web` e `db`)
- **Alternativa(s):** Deploy manual em VM, PaaS (Heroku/Render) sem
  containerização
- **Justificativa:** reprodutibilidade do ambiente entre máquinas da equipe
  e produção, facilidade de subir banco + aplicação com um único comando,
  portabilidade para qualquer provedor que suporte containers.

## 8. Diagrama Inicial

```
┌─────────────────────────────────────────────────────────────┐
│                         Usuário (Browser)                   │
└───────────────────────────────┬─────────────────────────────┘
                                 │ HTTP
                                 ▼
┌─────────────────────────────────────────────────────────────┐
│  Container "web"                                             │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ Gunicorn (WSGI)                                      │    │
│  │   └── Django (projeto "setup")                       │    │
│  │         └── App "agendamentos"                       │    │
│  │               ├── views.py   (lógica de requisição)  │    │
│  │               ├── models.py  (ORM)                   │    │
│  │               ├── forms.py                           │    │
│  │               ├── templates/ (SSR + Flatpickr JS)     │    │
│  │               └── static/    (CSS)                    │    │
│  └─────────────────────────────────────────────────────┘    │
└───────────────────────────────┬─────────────────────────────┘
                                 │ psycopg2 (SQL)
                                 ▼
┌─────────────────────────────────────────────────────────────┐
│  Container "db" — PostgreSQL 15                              │
│  (volume persistente: postgres_data)                          │
└─────────────────────────────────────────────────────────────┘

Orquestração: docker-compose.yml (depends_on + healthcheck)
```

**Fluxo resumido:** o navegador faz uma requisição HTTP → Django processa a
view, valida permissões do perfil do usuário → ORM consulta/grava no
PostgreSQL → Django renderiza o template HTML (SSR) → resposta volta ao
navegador, com Flatpickr tratando a seleção de data/hora no cliente.
