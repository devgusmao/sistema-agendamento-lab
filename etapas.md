# Etapas de Correção — Sistema de Agendamento de Laboratórios

> Gerado por análise estática (python não está instalado neste ambiente, então
> os testes **não foram executados**). Cada etapa é independente e deve terminar
> com `python manage.py test` verde antes de seguir para a próxima.

Legenda: 🔴 crítico · 🟠 importante · 🟡 melhoria

---

## 📍 Situação atual (atualizado em 23/11/2026)

| Etapa | Situação |
|---|---|
| 0–6 | ✅ Concluídas e validadas |
| 7 — Testes e CI | ✅ CI no GitHub Actions (migrações em dia + testes em PostgreSQL 15). 166 testes passando; suíte em ~5 s |
| 8 — Financeiro | ✅ Multa por cancelamento, status de pagamento e estorno com registro manual (migração 0012). Faltam descontos por perfil, preço por horário e comprovante |
| 9 — Agendamento avançado | ⏳ Pendente |
| 10 — Relatórios | ⏳ Pendente (dashboard financeiro já mostra multas, recebido, a receber e estornos) |
| 11 — Comportamento e penalidades | ⏳ Pendente |

Branches mergeados: `feat/regras-agendamento-e-tipos-precos`, `chore/deploy-gunicorn-whitenoise`, `feat/ci-e-limite-login` e `feat/usuarios-e-notificacoes` (PR #5). Em andamento: `feat/servicos-valores-e-multas` (camada de serviços, multa e pagamento).

**Refactor (23/11/2026):** a regra de negócio saiu de `views.py` para `agendamentos/servicos/` (`regras`, `reservas`, `precos`, `pagamentos`, `financeiro`, `solicitacoes`, `catalogo`) e de `usuarios.py`. As views só tratam de requisição e resposta. O comportamento anterior foi mantido: os 123 testes originais passaram sem alteração.

**Já existe (não refazer):** `valor_hora_aplicado` por reserva, `TipoAgendamento` (modos fixo/gratuito, duração máxima própria), e-mails por SMTP configuráveis pela tela, limite de reservas ativas, blocos de 30 min, multa de cancelamento, pagamento/estorno manual.

**Próximas etapas a executar (ordem sugerida):** 9 → 10 → 11.

### Pendências extras para a etapa 8
- [ ] Desconto automático por perfil de usuário (aluno × comunidade externa) — hoje só dá para criar tipos distintos.
- [ ] Preço diferente por laboratório ou por horário (pico/fora de pico), se a gestão quiser.
- [ ] Revisar os valores de cada tipo na tela "Tipos e Preços" após a migração (foram preenchidos pela média das tarifas antigas das máquinas).
- [ ] Notificar por e-mail a aprovação de cadastro e a conclusão de solicitações de software.
- [ ] Configurar o Gmail (senha de app) no `.env` de produção e testar o envio real.

---

## Etapa 0 — Preparar ambiente
- [ ] Instalar Python 3.11 + `pip install -r requirements.txt` (ou usar `docker compose run web python manage.py test`).
- [ ] Rodar `python manage.py test` e `python manage.py makemigrations --check` para obter a linha de base.
- [ ] Anotar testes que já falham antes de mexer em qualquer coisa.

---

## Etapa 1 — Controle de acesso 🔴 ✅ CONCLUÍDA (6 testes novos, 54/54 passando em SQLite)
Arquivos: [models.py](agendamentos/models.py), [decorators.py](agendamentos/decorators.py), [views.py](agendamentos/views.py)

1. **Admin/Técnico revogado continua com acesso.** `perfil_e_admin` e `perfil_e_gestor` ignoram `perfil.aprovado`. Um ADMIN/TÉCNICO com `aprovado=False` ainda passa em `admin_required`/`gestor_required`.
   - Correção: exigir `perfil_aprovado(user)` dentro de `perfil_e_admin` e `perfil_e_gestor` (superusuário continua liberado).
2. **`cancelar_agendamento`, `alterar_senha` usam só `@login_required`**, então conta pendente/revogada ainda age. Trocar por `@aprovado_required` em `cancelar_agendamento`.
3. **`editar_usuario` não protege superusuário**: `permissoes_acesso` e `resetar_senha_usuario` bloqueiam ADMIN comum de mexer em superusuário, mas `editar_usuario` permite alterar e-mail/username/tipo dele. Aplicar a mesma guarda.
4. **`aprovar_usuario`/`revogar_usuario`**: ADMIN comum pode revogar outro ADMIN. Decidir a regra e documentar (sugestão: só superusuário revoga ADMIN).
5. Templates repetem `user.is_superuser or user.perfil.tipo == ...` ([base.html](agendamentos/templates/agendamentos/base.html), softwares, laboratorios). Expor `is_admin`/`is_gestor` via context processor para ter uma única fonte de verdade.
- Testes: ADMIN com `aprovado=False` recebe redirect em todas as rotas `gestao/*`.

---

## Etapa 2 — Integridade de dados e histórico financeiro 🔴 ✅ CONCLUÍDA (61 testes passando; migração 0004)
Arquivo: [models.py](agendamentos/models.py) + nova migração

1. `Agendamento.usuario` e `Agendamento.computador` usam `CASCADE`: excluir usuário ou máquina **apaga reservas e receita do dashboard**. Trocar para `PROTECT` (ou `SET_NULL` + snapshot) e tratar o erro nas views de exclusão (`deletar_usuario`).
2. `Computador.laboratorio` com `CASCADE` tem o mesmo problema; usar `PROTECT` (a view já bloqueia, o banco também deve).
3. `valor_total` é calculado na criação e não guarda a tarifa usada. Guardar `valor_hora_aplicado` para auditoria.
4. Não existe rota de **exclusão de computador** (só criar/editar). Criar com `@admin_required @require_POST`, bloqueando se houver reservas.
5. `Laboratorio.capacidade` nunca é validada contra o número de máquinas. Validar em `ComputadorForm.clean()`.
- Gerar migração e testar em banco com dados.

---

## Etapa 3 — Lógica de agendamento 🔴 ✅ CONCLUÍDA (70 testes passando; + e-mail SMTP via .env; itens 1,2,3,4,5,6,7)
Arquivos: [forms.py](agendamentos/forms.py), [views.py](agendamentos/views.py) (`criar_agendamento`)

1. **Máquina em manutenção/inativa mantém reservas futuras confirmadas.** Ao editar status para `MANUTENCAO`/`INATIVO` em `editar_computador`, listar/cancelar reservas futuras afetadas (com `cancelado_por` e aviso ao usuário).
2. **Mesmo usuário pode reservar várias máquinas no mesmo horário.** Adicionar checagem de sobreposição por usuário (ou definir que é permitido).
3. **Sem limite de reservas ativas por usuário** — um aluno pode lotar o laboratório. Definir limite (ex.: N futuras).
4. Tolerância de 5 min no passado + sem duração mínima: reservas de 1 minuto passam. Validar duração mínima e alinhar minutos a blocos (15/30 min).
5. Sem horário de funcionamento do laboratório: é possível reservar às 3h. Definir janela por laboratório.
6. `DURACAO_MAXIMA` (2h) e `ANTECEDENCIA_MAXIMA` (30 dias) fixos no código; mover para `settings.py`.
7. Em caso de conflito, a view re-renderiza com o form preenchido, mas `reservas_json` é calculado **antes** do POST — recalcular após o erro.
- Testes: conflito, usuário duplo-reservando, máquina em manutenção.

---

## Etapa 4 — Solicitações de software 🟠 ✅ CONCLUÍDA (77 testes passando; migração 0005; software vinculado por nome, sem FK)
Arquivos: [views.py](agendamentos/views.py), [models.py](agendamentos/models.py)

1. Status `CONCLUIDO` **não instala o software no inventário** (`Computador.softwares`). `software_nome` é texto livre, desconectado de `Software`. Opção: vincular a `Software` (FK) e, ao concluir, adicionar ao(s) computador(es).
2. `cancelar_solicitacao` **deleta** o registro; trocar por status `CANCELADO` para manter histórico.
3. `atualizar_status_solicitacao` aceita qualquer transição (CONCLUIDO → PENDENTE). Definir transições válidas.
4. Solicitação feita para máquina em `INATIVO` é aceita; validar.

---

## Etapa 5 — Dashboard e relatórios 🟠 ✅ CONCLUÍDA (84 testes passando)
Arquivo: [views.py](agendamentos/views.py) (`dashboard_financeiro`, `meus_agendamentos`)

1. Receita inclui **reservas futuras** ainda não realizadas. Separar "receita realizada" × "prevista".
2. `horas_reservadas` itera todos os agendamentos em Python; calcular via agregação (`Sum(F('fim') - F('inicio'))`).
3. Sem filtro de período (mês/semestre) — tudo é acumulado desde o início.
4. `total_gasto` em `meus_agendamentos` soma reservas futuras como "gasto".
5. Conferir se `Count(distinct=True)` + `Sum` em `summary` não superconta ao adicionar novos joins.

---

## Etapa 6 — Configuração e deploy 🟠 ✅ CONCLUÍDA (gunicorn + WhiteNoise + Dockerfile não-root + compose dev/prod; validado em Docker)
Arquivos: [settings.py](setup/settings.py), [docker-compose.yml](docker-compose.yml), [Dockerfile](Dockerfile), [.env.example](.env.example)

1. `docker-compose` roda `runserver`, mas `requirements.txt` tem `gunicorn`. Usar gunicorn em produção.
2. Sem `collectstatic` nem WhiteNoise: com `DEBUG=False` o CSS não é servido.
3. Dockerfile roda como root e não tem `CMD`; criar usuário não-root.
4. `.env.example` vem com `DEBUG=True`; documentar claramente a diferença dev × prod.
5. Remover `SECURE_BROWSER_XSS_FILTER` (obsoleto no Django 4.x).
6. `volumes: .:/app` em produção sobrescreve a imagem; manter só em dev.
7. Duplicidade de `latex.main.tex` (raiz e `Documentação/`) e `STACK_ARQUITETURA.md` solto — consolidar.

---

## Etapa 7 — Testes e qualidade ✅ CONCLUÍDA (CI ativa; 166 testes; testes novos em `tests_multas.py`; `tests.py` ainda não foi dividido em pacote)
1. Cobrir as correções das etapas 1–5 em [tests.py](agendamentos/tests.py) (hoje ~59 testes, sem casos de perfil revogado nem máquina em manutenção).
2. Separar `tests.py` em pacote `tests/` por domínio.
3. Adicionar CI (GitHub Actions) com `manage.py test` + `makemigrations --check`.
4. Revisar `README.md` conforme as regras finais.

---

## Etapa 8 — Módulo financeiro (cobrança) 🔴 — ✅ CONCLUÍDA em 23/11/2026 (multa, pagamento e estorno manuais); descontos por perfil, preço por horário e comprovante ficaram de fora
> Hoje: o valor é calculado pelo tipo de agendamento (valor por hora próprio, sem preço na máquina) e gravado na reserva. Não existe pagamento, desconto por perfil, multa nem estorno. **Decisões de negócio marcadas com ❓ precisam ser confirmadas pela gestão antes de implementar.**

**Decisões tomadas (23/11/2026):** multa por antecedência (padrão: cancelar com menos de 24 h paga 50% do valor; configurável por `AGENDAMENTO_MULTA_HORAS` e `AGENDAMENTO_MULTA_PERCENTUAL`); reserva gratuita nunca gera multa; cancelamento feito pela administração ou por manutenção da máquina nunca gera multa; pagamento e estorno são registrados à mão pelo administrador (não há gateway online).

**8.1 Modelo de dados**
- [x] Campos em `Agendamento` (em vez de tabela `Pagamento` separada): `multa`, `status_pagamento` (`PENDENTE/PAGO/ESTORNADO/ISENTO`), `valor_pago`, `valor_estornado`, `pago_em`, `estornado_em`, `pagamento_registrado_por` (migração 0012, com classificação das reservas antigas).
- [ ] Forma de pagamento (PIX, dinheiro, cartão) e tabela de preços por horário/perfil.

**8.2 Regras de preço**
- [x] Cálculo centralizado em serviços: `TipoAgendamento.calcular_valor` e `servicos/precos.py` (multa).
- [ ] ❓ Isenção/desconto por perfil e por finalidade.
- [ ] ❓ Arredondamento do tempo (hoje é proporcional ao segundo).
- [ ] ❓ Pacotes/créditos pré-pagos.

**8.3 Cobrança e ciclo de pagamento**
- [x] Tela de gestão de reservas com "Registrar pagamento" e "Registrar estorno" (`servicos/pagamentos.py`).
- [x] Usuário vê "A pagar (uso e multas)", a multa prevista antes de cancelar e o estorno a receber.
- [ ] Comprovante simples.
- [ ] Expirar reserva não paga e bloquear reservas de quem tem débito acima de um limite.

**8.4 Cancelamento e estorno**
- [x] Cancelamento grátis até 24 h antes; depois, multa percentual.
- [x] Cancelamento por manutenção não gera multa; se já estava paga, fica com estorno pendente para o administrador devolver.
- [x] `valor_estornado` registrado; o dashboard mostra "Recebido (líquido de estornos)", "A receber", "Multas aplicadas" e "Estornos a devolver".

**8.5 Consistência**
- [x] Mudança de `valor_hora` nunca altera reservas já feitas (usar `valor_hora_aplicado`).
- [x] Operações financeiras em `transaction.atomic()` com trava de linha (cancelar e pagar ao mesmo tempo não se sobrescrevem). Falta log de auditoria completo (valor anterior).
- [x] Testes de multa, arredondamento, pagamento, estorno, dashboard e migração de dados. Desconto e horário de pico não existem ainda.

---

## Etapa 9 — Regras de agendamento avançadas 🟠
- [ ] **Check-in/check-out**: usuário confirma presença; sem check-in em 15 min a reserva vira `NAO_COMPARECEU` e libera a máquina.
- [ ] Novos status em `Agendamento`: `NAO_COMPARECEU`, `CONCLUIDO`, `EM_USO` (hoje só CONFIRMADO/CANCELADO e `em_andamento` é calculado).
- [ ] **Tempo real de uso** × tempo reservado (cobrar o que foi usado ou o reservado? ❓).
- [ ] Limite de reservas ativas e de horas por semana por perfil.
- [ ] Reserva recorrente (ex.: toda terça 14h) para professores, com checagem de conflito em lote.
- [ ] Reserva de **laboratório inteiro** (aula/evento), bloqueando todas as máquinas.
- [ ] Lista de espera quando o horário está ocupado; notifica quando liberar.
- [ ] Bloqueios de calendário (feriados, manutenção programada) por laboratório.
- [ ] Notificação por e-mail: confirmação, lembrete 1h antes, cancelamento.

---

## Etapa 10 — Relatórios 🟠
Hoje só existe `dashboard_financeiro` (totais acumulados, sem filtro).

- [ ] Filtros comuns: período, laboratório, máquina, perfil, finalidade.
- [ ] **Financeiro**: receita realizada × prevista × estornada; inadimplência; receita por dia/semana/mês (gráfico).
- [ ] **Ocupação**: % de horas reservadas ÷ horas disponíveis por lab/máquina; horários de pico; máquinas ociosas.
- [ ] **Comportamento**: taxa de cancelamento, no-show, antecedência média, duração média, finalidades mais usadas.
- [ ] **Usuários**: ranking de uso, reincidentes em no-show/cancelamento (usar identificador interno, evitando expor dados pessoais desnecessários — LGPD).
- [ ] **Manutenção/TI**: tempo médio de atendimento das solicitações, softwares mais pedidos.
- [ ] Exportação CSV/PDF restrita a admin, com log de quem exportou.
- [ ] Agregações no banco (não em laço Python); índices para as consultas novas.

---

## Etapa 11 — Comportamento e penalidades 🟡
- [ ] ❓ Regra de advertência: N no-shows em 30 dias → bloqueio temporário de reservas.
- [ ] Campo `bloqueado_ate` em `Perfil` e verificação em `criar_agendamento`.
- [ ] Cancelamentos tardios repetidos pesam na mesma pontuação.
- [ ] Gestor pode perdoar/remover penalidade (com justificativa registrada).
- [ ] Histórico de ações por usuário visível ao admin (auditoria).

---

## Ordem sugerida
`0 → 1 → 2 → 3 → 4 → 5 → 6 → 7` corrige o que está quebrado. Depois, as novas funcionalidades: `8 → 9 → 10 → 11` (a 8 vem antes porque 10 e 11 dependem dos dados financeiros e de status novos). As etapas 1–3 mexem em regras de negócio e segurança; 6–7 podem rodar em paralelo.
