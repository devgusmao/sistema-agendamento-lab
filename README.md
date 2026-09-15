# 💻 Sistema de Agendamento para Laboratórios de Informática

**🌐 Portal do Projeto:** [Acesse o site oficial do LabManager](https://sites.google.com/view/labmanager-devops/in%C3%ADcio)

Sistema web desenvolvido em **Python + Django + PostgreSQL**, containerizado via **Docker**, voltado para a gestão e reserva de computadores em espaços comunitários, telecentros, escolas públicas e bibliotecas.

O projeto busca resolver problemas comuns de filas presenciais, choque de horários e desorganização no controle de uso de computadores, promovendo a inclusão digital de forma estruturada.

---

## 👥 Equipe e Responsabilidades

| Foto / Usuário | Nome Completo | Papel no Projeto | GitHub |
| :---: | :--- | :--- | :---: |
| <img src="https://github.com/devgusmao.png" width="50px" style="border-radius:50%"> | Diego de Gusmão Gaseo | Lead Developer / DevOps & Arquitetura | [@devgusmao](https://github.com/devgusmao) |
| <img src="https://github.com/Erickzin00.png" width="50px" style="border-radius:50%"> | Erick Ayrton | Desenvolvedor Front-end | [@Erickzin00](https://github.com/Erickzin00) |
| <img src="https://github.com/ferrnand.png" width="50px" style="border-radius:50%"> | Fernando Oliveira | QA, UX & Site Administrator | [@ferrnand](https://github.com/ferrnand) |

---

## 🚀 Como executar

Pré-requisitos: Docker e Docker Compose.

```bash
git clone https://github.com/devgusmao/sistema-agendamento-lab.git
cd sistema-agendamento-lab

cp .env.example .env
# Gere uma SECRET_KEY única e ajuste as credenciais do banco no .env:
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"

docker compose up -d --build
docker compose exec web python manage.py createsuperuser
```

A aplicação fica disponível em **http://localhost:8001** e o painel do Django em
**http://localhost:8001/admin**.

As migrações são aplicadas automaticamente na subida do container `web`.

### Comandos úteis

```bash
docker compose exec web python manage.py test        # Suíte de testes
docker compose exec web python manage.py check       # Verificação do projeto
docker compose exec web python manage.py check --deploy  # Checklist de produção
docker compose logs -f web                           # Logs da aplicação
```

---

## 👤 Perfis de acesso

Todo cadastro entra como **Aluno não aprovado** e precisa da liberação de um
administrador antes de conseguir usar o sistema.

| Perfil | Pode fazer |
| :-- | :-- |
| **Aluno / Comunidade** | Reservar máquinas, cancelar as próprias reservas, solicitar instalação de software e acompanhar os próprios pedidos |
| **Técnico** | Tudo do Aluno, mais: gerenciar laboratórios, máquinas, inventário de softwares e atender solicitações de instalação |
| **Administrador** | Tudo do Técnico, mais: aprovar/revogar usuários, alterar permissões, ver e cancelar todas as reservas e acessar o dashboard financeiro |
| **Superusuário** | Administrador + painel `/admin` do Django |

---

## ✅ Funcionalidades

### Reservas
- Painel de máquinas com busca e filtros por laboratório, software e status.
- Reserva com seleção de data/hora (Flatpickr), limite de **2 horas** por reserva
  e antecedência máxima de **30 dias**.
- Prévia do custo calculada em tempo real a partir da tarifa por hora da máquina.
- Bloqueio de horários sobrepostos com trava no banco (`select_for_update`).
- Calendário lateral com os horários já ocupados da máquina.
- **Cancelamento pelo próprio usuário**, com histórico de quem cancelou e quando.
- Separação entre "próximas reservas" e "histórico", com total acumulado.

### Solicitações de software
- Pedido de instalação avulso ou vinculado a uma máquina específica.
- Destino gravado por máquina **ou** por laboratório.
- Fluxo de status: Pendente → Em Andamento → Concluído/Rejeitado, com registro
  do técnico responsável.
- O solicitante pode retirar um pedido ainda pendente.
- Cartões de status funcionam como filtro.

### Gestão
- CRUD de laboratórios, máquinas e inventário de softwares.
- Aprovação e revogação de acesso de usuários.
- Edição de usuários e alteração de nível de permissão.
- Gestão global de reservas com filtros por usuário, status e período.
- Dashboard financeiro: receita por laboratório e por máquina, total de horas
  reservadas e distribuição por finalidade de uso.

### Transversais
- Paginação em todas as listagens.
- Mensagens de feedback diferenciadas por nível (sucesso, erro, aviso, informação).
- Suíte de testes de regressão cobrindo as regras críticas.

---

## 🛠️ Stack Tecnológica

* **Linguagem:** Python 3.11+
* **Framework Web:** Django 4.2
* **Banco de Dados:** PostgreSQL 15 (Alpine)
* **Containerização:** Docker & Docker Compose
* **Driver de Banco:** `psycopg2-binary`
* **Gerenciamento de Segredos:** `python-decouple`
* **Front-end:** Templates Django + CSS próprio, Flatpickr para seleção de data/hora

---

## 🗄️ Modelo de Dados

Todos os modelos abaixo estão **implementados**.

#### `Perfil`
Estende o `auth_user` do Django com papel e status de aprovação. Criado
automaticamente por signal no cadastro do usuário.
* `usuario`: `OneToOneField` → `User`
* `tipo`: `ALUNO` | `TECNICO` | `ADMIN`
* `aprovado`: `BooleanField`

#### `Laboratorio`
* `nome`: `CharField` — único
* `capacidade`: `PositiveIntegerField`
* `descricao`: `TextField` (opcional)

#### `Software`
* `nome`, `versao`: únicos em conjunto
* `categoria`: `DEV` | `BD` | `UTIL` | `JOGOS`

#### `Computador`
* `identificador`: `CharField` — único **por laboratório**
* `laboratorio`: `ForeignKey` → `Laboratorio`
* `status`: `DISPONIVEL` | `MANUTENCAO` | `INATIVO`
* `softwares`: `ManyToManyField` → `Software`
* `valor_hora`: `DecimalField` — tarifa de co-working
* `observacoes`: `TextField` (opcional)

#### `Agendamento`
* `usuario`: `ForeignKey` → `User`
* `computador`: `ForeignKey` → `Computador`
* `data_hora_inicio` / `data_hora_fim`: `DateTimeField` (fim > início, garantido por constraint)
* `status`: `CONFIRMADO` | `CANCELADO`
* `finalidade`: `ESTUDO` | `PROGRAMACAO` | `ADMINISTRATIVO` | `JOGOS`
* `valor_total`: `DecimalField` — calculado pela duração × tarifa
* `criado_em`, `cancelado_em`, `cancelado_por`: rastreabilidade

#### `SolicitacaoInstalacao`
* `usuario`: `ForeignKey` → `User`
* `computador` / `laboratorio`: destino do pedido (ambos opcionais)
* `software_nome`, `justificativa`
* `status`: `PENDENTE` | `EM_ANDAMENTO` | `CONCLUIDO` | `REJEITADO`
* `atendido_por`, `data_criacao`, `data_atualizacao`

---

## 🔒 Segurança

As práticas adotadas, os controles já implementados e as pendências conhecidas
estão documentados em [SECURITY.md](SECURITY.md).

Em resumo: toda operação que altera estado exige `POST` com token CSRF, os
papéis são verificados por decoradores centralizados, os valores vindos do
cliente são validados contra as listas de escolhas dos modelos e a `SECRET_KEY`
é obrigatória em produção.

---

## 📂 Estrutura de Arquivos do Projeto

```text
sistema-agendamento-lab/
├── agendamentos/                # App principal da aplicação
│   ├── migrations/              # Histórico versionado do esquema do Postgres
│   ├── static/agendamentos/css/ # Folhas de estilo (styles, base, home, auth)
│   ├── templates/agendamentos/  # Telas do sistema
│   ├── admin.py                 # Registro dos modelos no Django Admin
│   ├── decorators.py            # Controle de acesso por papel e aprovação
│   ├── forms.py                 # Formulários e validações de negócio
│   ├── models.py                # Modelos, constraints e helpers de papel
│   ├── tests.py                 # Testes de regressão
│   ├── urls.py                  # Rotas do app
│   └── views.py                 # Lógica das telas
├── setup/                       # Configuração global do projeto Django
│   ├── settings.py              # Banco, segurança, apps instalados
│   └── urls.py                  # Mapeamento de rotas e do Admin
├── Documentação/                # Documentação acadêmica (LaTeX)
├── .dockerignore                # Impede que o .env entre na imagem
├── .env.example                 # Modelo das variáveis de ambiente
├── .gitignore                   # Proteção contra envio de arquivos sensíveis
├── docker-compose.yml           # Orquestração dos containers (Web + Postgres)
├── Dockerfile                   # Build da imagem Python com dependências
├── manage.py                    # Script CLI do Django
├── README.md                    # Este arquivo
├── SECURITY.md                  # Política e controles de segurança
└── requirements.txt             # Dependências Python do projeto
```

---

## 🧭 Próximos passos

- [ ] Servir com `gunicorn` + WhiteNoise no lugar do `runserver`.
- [ ] Limite de tentativas de login (proteção contra força bruta).
- [ ] Notificação por e-mail na aprovação de cadastro e na conclusão de solicitações.
- [ ] Exportação do dashboard financeiro em CSV/PDF.
- [ ] Trilha de auditoria completa das ações administrativas.
