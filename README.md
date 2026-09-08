# Sistema de Agendamento para Laboratórios


## 👥 Equipe e Responsabilidades

| Foto / Usuário | Nome Completo | Papel no Projeto | GitHub |
| :---: | :--- | :--- | :---: |
| <img src="https://github.com/devgusmao.png" width="50px" style="border-radius:50%"> | Diego de Gusmão Gaseo | Lead Developer / DevOps & Arquitetura | [@devgusmao](https://github.com/devgusmao) |
| <img src="https://github.com/GITHUB_USUARIO2.png" width="50px" style="border-radius:50%"> | Nome do Integrante 2 | Backend (Django / Database) | [@GITHUB_USUARIO2](https://github.com/GITHUB_USUARIO2) |
| <img src="https://github.com/GITHUB_USUARIO3.png" width="50px" style="border-radius:50%"> | Nome do Integrante 3 | Frontend / Documentação LaTeX | [@GITHUB_USUARIO3](https://github.com/GITHUB_USUARIO3) |


## 🗄️ Estrutura do Banco de Dados (PostgreSQL)

### Modelos Atuais

#### 1. Usuários (`CustomUser` / `auth_user`)
Armazena a identificação do usuário e seu tipo de perfil na comunidade.
* `id`: PK
* `username`: Identificador / Matrícula
* `email`: E-mail para contato
* `tipo_perfil`: Student | Teacher | Community Member

#### 2. Laboratório (`Laboratorio`)
* `id`: PK
* `nome`: Nome da sala/espaço (ex: Lab 01)
* `capacidade`: Quantidade total de máquinas

#### 3. Computador (`Computador`)
* `id`: PK
* `laboratorio`: FK -> `Laboratorio`
* `numero_maquina`: Identificador físico da máquina (ex: PC-05)
* `status`: Ativo | Manutenção | Inativo

#### 4. Agendamento (`Agendamento`)
* `id`: PK
* `usuario`: FK -> `User`
* `computador`: FK -> `Computador`
* `data_hora_inicio`: Datetime de início da reserva
* `data_hora_fim`: Datetime de término da reserva
* `status`: Confirmado | Cancelado | Concluído