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
| <img src="https://github.com/codeyCaz.png" width="50px" style="border-radius:50%"> | Cassio Vinicius | Desenvolvedor Back-End | [@codeyCaz](https://github.com/codeyCaz) |
| <img src="https://github.com/MatheusSalvador1.png" width="50px" style="border-radius:50%"> | Matheus Salvador | DevOps & Arquitetura | [@MatheusSalvador1](https://github.com/MatheusSalvador1) |
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

Na subida, o container `web` aplica as migrações, coleta os arquivos estáticos
(servidos por WhiteNoise) e inicia o **gunicorn** como usuário sem privilégios.

Para desenvolvimento, com código montado do host e recarga automática:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

### E-mail e notificações

A conta Gmail que envia as notificações é configurada **pela tela de administração**
(menu "E-mail (Gmail)"): informe a conta e a *senha de app* do Google (nunca a senha
da conta). A senha é guardada cifrada no banco e não volta para a tela; há um botão
de teste. Alternativa: `EMAIL_HOST_USER` e `EMAIL_HOST_PASSWORD` no `.env`, usadas
quando nada foi salvo na tela. Sem nenhuma das duas, as mensagens só aparecem no log.

O menu "Notificações" lista tudo o que o sistema avisa (reserva confirmada/cancelada,
nova reserva e cancelamento feito pelo usuário para os administradores,
lembrete, novo cadastro, cadastro aprovado, acesso revogado, senha redefinida e
solicitações de software), permite ligar/desligar cada evento e mostra o histórico de
envios (sem guardar endereços de e-mail).

**Lembretes de reserva** exigem agendar o comando abaixo no servidor (ex.: a cada 15 min):

```bash
*/15 * * * * docker compose exec -T web python manage.py enviar_lembretes
```

A antecedência é `AGENDAMENTO_LEMBRETE_HORAS` (padrão 2). As regras de agendamento
(duração, blocos, limite de reservas, horário e multa de cancelamento) também são ajustáveis pelo `.env`;
veja o `.env.example`.

### Cadastro com confirmação de e-mail e recuperação de senha

Os dois fluxos usam um **código numérico de 6 dígitos** enviado por e-mail (sem link, então
funcionam mesmo com o sistema fora da internet).

- **Cadastro:** o usuário recebe o código (válido por 30 min) e o digita na tela "Confirmar
  e-mail" junto com o e-mail do cadastro. Só depois de confirmar, os administradores são
  avisados. O acesso continua exigindo a aprovação de um administrador, e a tela de aprovação
  mostra se o e-mail já foi confirmado.
- **Esqueci minha senha:** o código vale por 15 min e é de uso único. O usuário informa o
  e-mail, o código e a nova senha numa tela só, com as regras de senha do sistema. O código só
  é gasto se a senha for aceita. Quem já está aprovado volta a entrar sem nova aprovação; conta
  nova continua aguardando o administrador.
- **Proteções do código curto:** guardado só como HMAC com a `SECRET_KEY`; no máximo 5 erros por
  código (depois é preciso pedir outro); um código novo invalida o anterior; limite de 3
  pedidos por hora por usuário, 10 por IP e 20 tentativas de digitação por IP.
- **Segurança:** resposta igual exista ou não o e-mail; as sessões abertas caem ao trocar a
  senha; o login travado por tentativas é liberado; e o dono recebe um alerta de senha alterada.
- Validades e limites no `.env.example`. Sem e-mail configurado (Gmail), os códigos só aparecem
  no log e ninguém consegue confirmar.

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
| **Administrador** | Tudo do Técnico, mais: aprovar/revogar e gerenciar usuários, configurar e-mail e notificações, ver e cancelar todas as reservas e acessar o dashboard financeiro |
| **Superusuário** | Administrador + painel `/admin` do Django |

---

## ✅ Funcionalidades

### Reservas
- Painel de máquinas com busca e filtros por laboratório, software e status.
- Reserva com seleção de data/hora (Flatpickr), limite de **2 horas** por reserva
  e antecedência máxima de **30 dias**.
- Prévia do custo calculada em tempo real a partir da tarifa por hora do tipo de agendamento.
- **Multa de cancelamento:** quem cancela a própria reserva paga com menos de 24 h de antecedência paga 50% do valor (ambos configuráveis). Reservas gratuitas e cancelamentos feitos pela administração ou por manutenção da máquina não geram multa. A tela avisa o valor da multa antes de cancelar.
- **Pagamento e estorno (registro manual):** cada reserva tem status de pagamento (Pendente, Pago, Estornado ou Isento). O administrador registra o recebimento e a devolução na tela de gestão de reservas; não há gateway de pagamento online.
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
- Edição de usuários, tipo de perfil e acesso em um só lugar (Gerenciar Usuários). Só superusuários promovem a administrador ou rebaixam/revogam administradores.
- Notificações por e-mail configuráveis, com histórico, e tela para configurar o Gmail.
- Gestão global de reservas com filtros por usuário, status e período.
- Dashboard financeiro: receita por laboratório e por máquina, total de horas
  reservadas, distribuição por tipo de agendamento, multas aplicadas, valor
  recebido (líquido de estornos), a receber e estornos a devolver.
- Tipos de agendamento e preços configuráveis (tela "Tipos e Preços").

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
* `observacoes`: `TextField` (opcional)

#### `Agendamento`
* `usuario`: `ForeignKey` → `User`
* `computador`: `ForeignKey` → `Computador`
* `data_hora_inicio` / `data_hora_fim`: `DateTimeField` (fim > início, garantido por constraint)
* `status`: `CONFIRMADO` | `CANCELADO`
* `tipo`: `ForeignKey` → `TipoAgendamento` (cadastro configurável pela administração)
* `valor_hora_aplicado` / `valor_total`: tarifa e total gravados no momento da reserva (mudanças de preço não alteram reservas já feitas)
* `multa`: valor cobrado quando o próprio dono cancela fora do prazo
* `status_pagamento`: `PENDENTE` | `PAGO` | `ESTORNADO` | `ISENTO`; `valor_pago`, `valor_estornado`, `pago_em`, `estornado_em`, `pagamento_registrado_por`
* `criado_em`, `cancelado_em`, `cancelado_por`: rastreabilidade

#### `TipoAgendamento`
* `nome`, `descricao`, `ativo`, `ordem`
* `modo`: `FIXO` (cobra `valor_hora` por hora de uso) | `GRATUITO`
* Todo valor é definido aqui; a máquina não tem preço próprio
* `duracao_maxima_min`: limite de duração específico do tipo (opcional)

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
│   ├── servicos/                # Regras de negócio (fora das views)
│   │   ├── regras.py            # Janela da reserva: duração, blocos, horário
│   │   ├── reservas.py          # Reservar e cancelar, com trava de concorrência
│   │   ├── precos.py            # Cálculo da multa de cancelamento
│   │   ├── pagamentos.py        # Registro manual de pagamento e estorno
│   │   ├── financeiro.py        # Totais do usuário e dashboard
│   │   ├── solicitacoes.py      # Fluxo das solicitações de software
│   │   └── catalogo.py          # Busca de máquinas da tela inicial
│   ├── tests.py                 # Testes de regressão
│   ├── tests_multas.py          # Testes de multa, pagamento e serviços
│   ├── urls.py                  # Rotas do app
│   ├── usuarios.py              # Regras de alteração e exclusão de usuários
│   └── views.py                 # Requisição e resposta (sem regra de negócio)
├── setup/                       # Configuração global do projeto Django
│   ├── settings.py              # Banco, segurança, apps instalados
│   └── urls.py                  # Mapeamento de rotas e do Admin
├── Documentação/                # Documentação acadêmica (LaTeX)
├── .dockerignore                # Impede que o .env entre na imagem
├── .env.example                 # Modelo das variáveis de ambiente
├── .gitignore                   # Proteção contra envio de arquivos sensíveis
├── docker-compose.yml           # Orquestração dos containers (Web + Postgres)
├── docker-compose.dev.yml       # Ajustes de desenvolvimento (runserver + volume)
├── Dockerfile                   # Build da imagem Python (usuário não-root)
├── entrypoint.sh                # Migra, coleta estáticos e inicia o gunicorn
├── manage.py                    # Script CLI do Django
├── README.md                    # Este arquivo
├── SECURITY.md                  # Política e controles de segurança
└── requirements.txt             # Dependências Python do projeto
```

---

## 🧭 Próximos passos

- [x] Limite de tentativas de login (django-axes: 5 falhas → bloqueio de 15 min por usuário+IP; ajustável no `.env`).
- [x] Notificações por e-mail (aprovação, solicitações, lembretes) com liga/desliga e histórico.
- [x] Multa de cancelamento, registro de pagamento e estorno (manual).
- [ ] Descontos por perfil, preço por horário e comprovante de pagamento.
- [ ] Check-in/check-out e controle de não comparecimento.
- [ ] Relatórios de ocupação e comportamento de uso.
- [x] Integração contínua (CI) com testes e verificação de migrações.
- [ ] Exportação do dashboard financeiro em CSV/PDF.
- [ ] Trilha de auditoria completa das ações administrativas.
