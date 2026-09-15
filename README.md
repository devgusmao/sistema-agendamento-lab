# 💻 Sistema de Agendamento para Laboratórios de Informática

Sistema web desenvolvido em **Python + Django + PostgreSQL**, containerizado via **Docker**, voltado para a gestão e reserva de computadores em espaços comunitários, telecentros, escolas públicas e bibliotecas. 

O projeto busca resolver problemas comuns de filas presenciais, choque de horários e desorganização no controle de uso de computadores, promovendo a inclusão digital de forma estruturada.

---

## 👥 Equipe e Responsabilidades

| Foto / Usuário | Nome Completo | Papel no Projeto | GitHub |
| :---: | :--- | :--- | :---: |
| <img src="https://github.com/devgusmao.png" width="50px" style="border-radius:50%"> | Diego de Gusmão Gaseo | Lead Developer / DevOps & Arquitetura | [@devgusmao](https://github.com/devgusmao) |
| <img src="https://github.com/Erickzin00.png" width="50px" style="border-radius:50%"> | Erick Ayrton | Desenvolvedor Front-end | [@Erickzin00](https://github.com/Erickzin00) |

## 📌 O que foi feito até o momento

- [x] **Configuração de Ambiente & Containerização:** Estruturação do ambiente isolado utilizando Docker Compose com dois serviços independentes (`web` para o Django e `db` para o PostgreSQL 15).
- [x] **Gestão de Segurança:** Isolamento de credenciais do banco e chaves de sessão do Django em variáveis de ambiente (`.env`) não versionadas no Git.
- [x] **Modelagem Inicial de Dados:** Criação do app `agendamentos` e implementação do modelo `Computador` com campos de status, identificador único e observações.
- [x] **Migrações e Banco de Dados:** Execução das migrações do Django ORM no PostgreSQL (`agendamentos_computador`), garantindo a integridade relacional e persistência de dados via volumes gerenciados.
- [x] **Painel Administrativo:** Customização e registro do modelo no Django Admin (`/admin`) com filtros de busca, exibição de campos estruturados e suporte a gerenciamento direto pelos administradores.

---

## 🛠️ Stack Tecnológica

* **Linguagem:** Python 3.11+
* **Framework Web:** Django 4.2+
* **Banco de Dados:** PostgreSQL 15 (Alpine)
* **Containerização:** Docker & Docker Compose
* **Driver de Banco:** `psycopg2-binary`
* **Gerenciamento de Segredos:** `python-decouple`

---

## 🗄️ Estrutura do Banco de Dados (PostgreSQL)

### Modelos de Dados

#### 1. Computador (`Computador`) — *Implementado*
Representa as máquinas físicas disponíveis no laboratório.
* `id`: `BigAutoField` (PK)
* `identificador`: `CharField` (ex: PC-01, PC-02) — Único
* `status`: `CharField` (`DISPONIVEL` | `MANUTENCAO` | `INATIVO`)
* `observacoes`: `TextField` (Opcional)

#### 2. Usuários (`CustomUser` / `auth_user`) — *Em expansão*
Controle de acesso e perfil dos membros da comunidade.
* `id`: `BigAutoField` (PK)
* `username`: `CharField` (Matrícula ou CPF)
* `email`: `EmailField`
* `tipo_perfil`: `CharField` (Aluno | Professor | Comunidade)

#### 3. Laboratório (`Laboratorio`) — *Planejado*
* `id`: `BigAutoField` (PK)
* `nome`: `CharField` (ex: Lab 01, Telecentro Central)
* `capacidade`: `IntegerField`

#### 4. Agendamento (`Agendamento`) — *Planejado*
* `id`: `BigAutoField` (PK)
* `usuario`: `ForeignKey` -> `User`
* `computador`: `ForeignKey` -> `Computador`
* `data_hora_inicio`: `DateTimeField`
* `data_hora_fim`: `DateTimeField`
* `status`: `CharField` (`CONFIRMADO` | `CANCELADO` | `CONCLUIDO`)

---

## 📂 Estrutura de Arquivos do Projeto

```text
sistema-agendamento-lab/
├── agendamentos/                # App principal da aplicação
│   ├── migrations/              # Histórico versionado de tabelas do Postgres
│   │   └── 0001_initial.py
│   ├── admin.py                 # Interface administrativa para a tabela Computadores
│   ├── models.py                # Definição das tabelas em ORM Python
│   └── views.py                 # Lógica das telas (em desenvolvimento)
├── setup/                       # Configuração global do projeto Django
│   ├── settings.py              # Integração com Postgres e apps instalados
│   └── urls.py                  # Mapeamento de rotas e rotas do Admin
├── .env                         # Variáveis de ambiente isoladas (Git-Ignored)
├── .gitignore                   # Proteção contra envio de arquivos sensíveis/locais
├── docker-compose.yml           # Orquestração dos containers (Web + Postgres)
├── Dockerfile                   # Build da imagem Python com dependências
├── manage.py                    # Script CLI do Django
├── README.md                    # Documentação do projeto
└── requirements.txt             # Dependências Python do projeto