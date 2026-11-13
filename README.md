# Backup Manager — Sistema Traz Valor

Painel para cadastrar bancos de dados, agendar backups automáticos, acompanhar o histórico e baixar as cópias em ZIP.

| Parte | Tecnologia | Função |
|---|---|---|
| Painel (frontend) | Vue 3 + Vite | Telas, formulários, histórico e dicas de correção de erros |
| API (backend) | Laravel 12 / PHP 8.3 | Login, cadastros, validações, fila e download |
| Executor (worker) | Python 3.12 | Agendamento, dump, compressão, criptografia, retenção e cópia externa |
| Banco de controle | PostgreSQL 16 (container próprio) | Usuários, bancos cadastrados, agendamentos, fila e histórico |
| Bancos copiados | **MySQL**, **PostgreSQL** e **SQLite** | Origem dos backups (somente leitura; os dados de origem não são alterados) |

Tudo roda em Docker. **Não é preciso instalar PHP, Python, Node ou Composer na máquina.**

---

## Sumário

1. [Requisitos](#1-requisitos)
2. [Instalação passo a passo](#2-instalação-passo-a-passo)
3. [Configurações usadas (portas, containers, volumes e variáveis)](#3-configurações-usadas)
4. [Roteiro de testes no painel](#4-roteiro-de-testes-no-painel)
5. [Testes automatizados](#5-testes-automatizados)
6. [Comandos úteis do dia a dia](#6-comandos-úteis-do-dia-a-dia)
7. [Problemas comuns e soluções](#7-problemas-comuns-e-soluções)
8. [Como o backup funciona por dentro](#8-como-o-backup-funciona-por-dentro)
9. [Segurança e chaves](#9-segurança-e-chaves)
10. [Restauração de um backup](#10-restauração-de-um-backup)
11. [Retenção, disco e cópia externa](#11-retenção-disco-e-cópia-externa)
12. [Colocando em produção](#12-colocando-em-produção)

---

## 1. Requisitos

| Item | Detalhe |
|---|---|
| Sistema operacional | Windows 10/11, Linux ou macOS (Intel ou Apple Silicon) |
| Docker | **Docker Desktop** (Windows/macOS) ou **Docker Engine + Docker Compose v2** (Linux) |
| Git | Para baixar o código do repositório |
| Memória | Pelo menos 4 GB livres para o Docker |
| Disco | ~3 GB para as imagens + espaço para os backups (dimensione pelo tamanho dos seus bancos) |
| Portas livres | **8190** (painel) e **5435** (PostgreSQL de controle). Podem ser trocadas no `.env` |
| Internet | Necessária no primeiro build (baixa imagens e pacotes) e para acessar os bancos remotos |

### Conferindo o Docker

Abra o terminal (no Windows: **PowerShell**) e rode:

```powershell
docker --version
docker compose version
```

Os dois comandos precisam mostrar uma versão. No Windows, o **Docker Desktop precisa estar aberto** (ícone da baleia na bandeja, com status *Running*).

> **Windows:** o Docker Desktop deve usar o backend **WSL 2** (padrão nas versões atuais). Em *Settings → Resources*, deixe ao menos 4 GB de memória.

---

## 2. Instalação passo a passo

### Passo 1 — Baixar o código

```powershell
git clone https://github.com/programadortrazvalor/SistemaBackup.git
cd SistemaBackup
```

> O repositório força finais de linha LF (`.gitattributes`). Não converta os arquivos para CRLF; scripts como `docker/entrypoint.sh` deixam de funcionar no container.

### Passo 2 — Criar o arquivo `.env`

Copie o modelo:

```powershell
# Windows (PowerShell)
Copy-Item .env.example .env
```

```bash
# Linux / macOS
cp .env.example .env
```

Abra o `.env` em um editor e **preencha obrigatoriamente** os dados do banco de controle (PostgreSQL que roda no container `db`). Os valores abaixo são exemplos; escolha os seus:

```dotenv
DB_DATABASE=trazvalor_backup
DB_USERNAME=trazvalor
DB_PASSWORD=TroquePorUmaSenhaForte123
```

Revise também, se necessário:

| Variável | Padrão | Quando mudar |
|---|---|---|
| `APP_PORT` | `8190` | Se a porta 8190 já estiver em uso na sua máquina |
| `DB_PORT` | `5435` | Se a porta 5435 já estiver em uso (é só a porta de acesso pelo host, ex.: DBeaver) |
| `APP_URL` | `http://localhost:8190` | Acompanhe o valor de `APP_PORT` |
| `APP_KEY` | vazio | **Deixe vazio.** A chave é gerada automaticamente no primeiro início (veja a [seção 9](#9-segurança-e-chaves)) |
| `BACKUP_ALERT_EMAIL` | vazio | Para receber e-mail quando um backup falhar (exige configurar `MAIL_*`) |

> **Importante:** `DB_DATABASE`, `DB_USERNAME` e `DB_PASSWORD` só são aplicados na **primeira** criação do volume do PostgreSQL. Se você mudar depois, o banco antigo não aceita as credenciais novas. Para recomeçar do zero em uma máquina de teste, veja [Começar do zero](#começar-do-zero-apaga-tudo).

### Passo 3 — Construir e subir os containers

```powershell
docker compose up -d --build
```

O primeiro build leva de 3 a 10 minutos (depende da internet). Ele instala PHP, Nginx, Python, os clientes `mysqldump`, `pg_dump` e `sqlite3`, e compila o painel Vue.

### Passo 4 — Conferir se tudo subiu

```powershell
docker compose ps
```

O resultado esperado tem três containers:

| Container | Status esperado |
|---|---|
| `Trazvalor-backup-db` | `Up ... (healthy)` |
| `Trazvalor-backup` | `Up ... (healthy)` (pode levar até 40 s para ficar *healthy*) |
| `Trazvalor-backup-worker` | `Up ...` |

Se algum não estiver de pé, veja os logs:

```powershell
docker compose logs --tail=100 app
docker compose logs --tail=100 worker
docker compose logs --tail=100 db
```

> As **migrations do banco rodam sozinhas** ao iniciar o container `app`. Não é preciso rodar `php artisan migrate`.

### Passo 5 — Criar o usuário administrador

```powershell
docker compose exec --user www-data app php artisan backups:install
```

O assistente pergunta, nesta ordem:

1. **Nome do administrador**
2. **E-mail de acesso** (usado no login)
3. **Senha do painel**: mínimo de **12 caracteres**, digitada duas vezes
4. **Celular**, **CPF** e **data de nascimento** (formato `AAAA-MM-DD`, ex.: `1990-05-20`)
5. **Senha MySQL do banco inicial**: somente na primeira instalação

Sobre o item 5: na primeira instalação o assistente cadastra um **banco de exemplo** (MySQL em `mysql29-farm15.uni5.net`, banco/usuário `dyisencoes01`) e um agendamento de **terça e sexta às 17h30**.
- Se você **não tem** essa senha, só aperte **Enter**: o banco é criado **inativo** e o agendamento fica pausado. Depois você edita ou exclui no painel e cadastra os seus bancos.
- A senha digitada é guardada criptografada; ela nunca fica no código.

O mesmo comando serve depois para **criar outro administrador ou trocar a senha** (ele pede confirmação e não recria bancos nem chaves).

### Passo 6 — Acessar o painel

Abra no navegador: **http://localhost:8190** (ou a porta que você definiu em `APP_PORT`).

Entre com o e-mail e a senha criados no passo 5.

No topo do painel deve aparecer o executor como conectado. Se aparecer **"O executor ainda não iniciou"** ou **"sem contato recente"**, veja [Problemas comuns](#o-painel-diz-que-o-executor-está-sem-contato).

**Pronto, a instalação está concluída.** Siga para o [roteiro de testes](#4-roteiro-de-testes-no-painel).

---

## 3. Configurações usadas

### Containers

| Serviço (compose) | Nome do container | Função |
|---|---|---|
| `db` | `Trazvalor-backup-db` | PostgreSQL 16 de controle (dados do sistema) |
| `app` | `Trazvalor-backup` | Nginx + PHP-FPM (painel e API). Roda as migrations ao iniciar |
| `worker` | `Trazvalor-backup-worker` | Executor Python: agenda, executa backups e aplica retenção. Verifica a fila a cada 15 s |

### Portas

| Porta no host | Destino | Uso |
|---|---|---|
| `127.0.0.1:8190` (`APP_PORT`) | `app:80` | Painel no navegador |
| `127.0.0.1:5435` (`DB_PORT`) | `db:5432` | Acesso opcional ao banco de controle (DBeaver, pgAdmin, psql) |

As duas portas ficam presas a `127.0.0.1`: só a própria máquina acessa.

### Volumes e pastas

| Volume / pasta | Montado em | Conteúdo |
|---|---|---|
| `pg_data` | `db:/var/lib/postgresql/data` | Banco de controle |
| `backup_data` | `app` e `worker`: `/data` | **Chaves** (`/data/app.key`, `/data/keys/`), **backups** (`/data/backups`) e temporários (`/data/tmp`) |
| `app_storage`, `worker_storage` | `/var/www/html/storage` | Logs e cache do Laravel |
| `./certs` (pasta do projeto) | `/certs` (somente leitura) | Certificados CA para conexões TLS (opcional) |
| `./sqlite` (pasta do projeto) | `worker:/sqlite` (somente leitura) | Arquivos SQLite locais a serem copiados (opcional) |

> **Nunca rode `docker compose down -v`** numa instalação que você quer manter: o `-v` apaga os volumes, ou seja, **chaves, backups e todo o cadastro**.

### Fuso horário e regras fixas

- Todo agendamento usa o fuso **America/Cuiaba** (UTC−04:00), independente do fuso da máquina.
- Agendamentos só podem ser **entre 17:01 e 23:59**. Backups de teste manuais rodam a qualquer hora.
- Um agendamento perdido (máquina desligada, por exemplo) ainda roda até **6 horas** depois, no mesmo dia; depois disso é cancelado.
- Os bancos são processados **um por vez**.

---

## 4. Roteiro de testes no painel

Siga na ordem para validar o sistema inteiro numa máquina nova.

### 4.1 Cadastrar um banco MySQL

1. Menu **Bancos de dados → Adicionar banco**.
2. Preencha:

| Campo | O que colocar |
|---|---|
| Nome do banco | Nome para exibir no painel (ex.: *Traz Valor*) |
| Tipo de banco | **MySQL** |
| Host MySQL | Endereço do servidor (ex.: `mysql.seudominio.com.br`), sem `http://` |
| Porta | `3306` |
| Banco de dados | Nome exato do banco no servidor |
| Usuário / Senha MySQL | Credenciais com permissão de leitura no banco |
| Conexão TLS | **Exigir TLS** se o servidor suporta; **Sem TLS / túnel externo** se não suporta (comum em hospedagens compartilhadas) |
| Arquivo CA | Opcional. Nome de um `.pem` colocado na pasta `certs/` |
| Consistência do backup | Veja a tabela abaixo |

| Consistência | Quando usar |
|---|---|
| **Transação InnoDB** | Banco só com tabelas InnoDB. Não bloqueia gravações |
| **Bloqueio das tabelas do banco (MyISAM)** | Banco com tabelas **MyISAM** (sistemas legados). Bloqueia gravações **só deste banco** durante a cópia. Exige a permissão `LOCK TABLES` |
| **Bloqueio global — legado** | Último recurso. Bloqueia a instância inteira e exige a permissão `RELOAD` (normalmente indisponível em hospedagem compartilhada) |

3. Deixe **Banco ativo** marcado e clique em **Salvar banco**.

> **Hospedagens (uni5, KingHost etc.):** libere o **IP público da sua máquina** no "Acesso remoto ao MySQL" do painel da hospedagem; sem isso, a conexão é recusada.

### 4.2 Cadastrar um banco PostgreSQL (opcional)

Mesmo formulário, com **Tipo de banco = PostgreSQL** e porta `5432`. A consistência é sempre por snapshot (sem bloqueio).

> O cliente `pg_dump` da imagem é a versão **16**. Ele copia servidores PostgreSQL **até a versão 16**. Para servidores mais novos, é preciso atualizar o pacote `postgresql-client` no `Dockerfile`.

### 4.3 Cadastrar um banco SQLite (opcional)

Há duas formas:

**a) Arquivo local**: copie o arquivo para a pasta `sqlite/` do projeto (ex.: `sqlite/sistema.sqlite`). No painel, use **Tipo = SQLite**, deixe o **Host em branco** e em "Arquivo na pasta sqlite/" informe só o nome: `sistema.sqlite`.

**b) Arquivo em servidor remoto (SFTP/SSH)**: **Tipo = SQLite**, preencha **Host SSH**, **Porta** (normalmente `22`), **Usuário SSH**, **Senha SSH** e o **caminho completo** do arquivo no servidor (ex.: `/home/usuario/app/database.sqlite`). O arquivo é baixado e o backup é gerado da cópia.
- Na primeira conexão a chave SSH do servidor é registrada. Se ela mudar depois, o backup é recusado por segurança.
- Prefira horários sem gravação no banco; cópia de SQLite em uso pode sair inconsistente.

### 4.4 Gerar um backup de teste

1. Em **Bancos de dados**, clique em **Gerar backup de teste** no banco cadastrado.
2. O sistema leva você ao **Histórico**. O status passa de *Na fila* → *Em execução* → *Concluído* (a tela atualiza sozinha a cada 10 s).
3. Abra **Detalhes da execução** para ver início, fim, SHA-256 e informações do dump.

### 4.5 Testar as dicas de erro

Force um erro de propósito, por exemplo com uma senha errada, e gere um backup de teste. No histórico, abaixo da execução que falhou, aparece um quadro amarelo com:

- **o que aconteceu**, em linguagem simples;
- **o passo a passo** para corrigir;
- o botão **Corrigir configuração do banco**, que abre o formulário com os campos a revisar **destacados em amarelo**.

Erros com dica pronta: TLS/SSL não suportado, certificado, usuário/senha recusados, banco inexistente, host não encontrado, servidor inacessível, tabelas MyISAM, falta de permissão de bloqueio, versão do PostgreSQL, arquivo SQLite/SSH, tempo limite, disco cheio e cópia externa.

### 4.6 Baixar o backup

No **Histórico**, clique no ícone de download de uma execução **Concluída**.

- O arquivo vem em **`.zip`** com o **`.sql` dentro**, já descriptografado e pronto para importar.
- Nome: `<nome-do-banco>_<data>_<hora>_job-<id>.zip`.
- O ZIP é gerado **enquanto é baixado**: o download começa na hora e **não tem limite de tempo** (serve para bancos legados enormes). O tamanho total só é conhecido no fim.
- No servidor o backup continua guardado **criptografado**.

### 4.7 Criar um agendamento

1. Menu **Agendamentos → Novo agendamento**.
2. Escolha o banco, os dias da semana e o horário (entre **17:01 e 23:59**, horário de Cuiabá).
3. Salve. O card mostra o horário e os dias escolhidos.

### 4.8 Testar banco inativo × agendamento

1. Em **Bancos de dados → Editar conexão**, desmarque **Banco ativo** e salve. Aparece o aviso de que os agendamentos do banco também foram pausados.
2. Em **Agendamentos**, o card mostra *"Pausado porque o banco está inativo"*.
3. Ao editar esse agendamento, a opção **Agendamento ativo** fica bloqueada, com o caminho para reativar o banco.
4. Reative o banco: os agendamentos dele voltam a ficar ativos.

### 4.9 Configurações

Em **Configurações**, teste: backups mantidos por banco (retenção), tempo máximo do dump, reserva mínima de disco e exigência de cópia externa. As mudanças valem para as **próximas** execuções.

---

## 5. Testes automatizados

Como os testes rodam em containers temporários, não é preciso instalar nada além do Docker. Rode a partir da pasta do projeto.

### Testes da API (PHP / PHPUnit)

```powershell
docker run --rm -v "${PWD}:/src:ro" composer:2 sh -c "cp -r /src /w && cd /w && rm -rf vendor && composer install -q --no-interaction --ignore-platform-reqs && php vendor/bin/phpunit"
```

Cobre: login/logout, senha criptografada e oculta na API, validação de horários e dias, fila sem duplicação, banco pausado, edição sem perder a senha, cadastros MySQL/PostgreSQL/SQLite (local e SSH), troca de tipo de banco e sincronização banco × agendamento.

### Testes do executor (Python)

```powershell
docker run --rm -v "${PWD}:/src:ro" python:3.12-slim sh -c "apt-get update -qq && apt-get install -y -qq sqlite3 >/dev/null && cp -r /src/python /w && cd /w && chmod +x tests/*.py && pip install -q -r requirements.txt && python -m unittest tests.test_worker -v"
```

Cobre: criptografia em blocos, gzip, adulteração e truncamento, chave errada, agendamento e fuso, senha escapada e ocultada, dump MySQL (simulado) incluindo MyISAM e modo de bloqueio de tabelas, `pg_dump` (simulado), SQLite local e via SFTP (simulado), proteção de caminhos, ZIP em arquivo e em fluxo, e cópia externa com checksum.

### Build do painel (Vue)

```powershell
docker run --rm -v "${PWD}:/src:ro" node:22-bookworm-slim sh -c "mkdir /w && cd /w && cp /src/package*.json /src/vite.config.js . && cp -r /src/resources . && npm ci --no-audit --no-fund && npx vite build"
```

> **Linux/macOS:** troque `${PWD}` por `"$(pwd)"`. **Windows com Git Bash:** prefixe o comando com `MSYS_NO_PATHCONV=1` e use o caminho completo da pasta (ex.: `-v "C:\caminho\SistemaBackup:/src:ro"`).

> O script `python/tests/integration_laravel.py` é da versão antiga com banco de controle em SQLite e **não reflete a versão atual** (PostgreSQL). Use os testes acima.

---

## 6. Comandos úteis do dia a dia

```powershell
# Status dos containers
docker compose ps

# Logs (acompanhar ao vivo: acrescente -f)
docker compose logs --tail=100 worker
docker compose logs --tail=100 app

# Reiniciar sem rebuild
docker compose restart

# Atualizar após baixar código novo (git pull)
git pull
docker compose up -d --build

# Parar tudo (os dados são preservados)
docker compose down

# Listar os backups guardados (criptografados)
docker compose exec --user www-data worker ls -lh /data/backups

# Criar outro administrador ou trocar senha
docker compose exec --user www-data app php artisan backups:install
```

### Acessar o banco de controle (DBeaver / pgAdmin)

| Campo | Valor |
|---|---|
| Host | `localhost` |
| Porta | valor de `DB_PORT` (padrão `5435`) |
| Banco / Usuário / Senha | `DB_DATABASE` / `DB_USERNAME` / `DB_PASSWORD` do `.env` |
| Schema | valor de `DB_SCHEMA` |

Tabelas principais: `sis_database_servers` (bancos), `sis_backup_schedules` (agendamentos), `sis_backup_runs` (histórico/fila), `sis_backup_settings` (configurações), `sis_usuarios` (acessos).

### Limpar o histórico para novos testes

Apaga **todas** as execuções e os arquivos de backup. Bancos, agendamentos e configurações são mantidos.

```powershell
docker compose exec db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "TRUNCATE sis_backup_runs RESTART IDENTITY"'
docker compose exec --user www-data worker sh -c 'rm -f /data/backups/*.sql.gz.enc'
```

> Se o seu `DB_SCHEMA` não for `public`, use `TRUNCATE <schema>.sis_backup_runs RESTART IDENTITY`.

### Começar do zero (apaga tudo)

Somente em máquina de teste: apaga **cadastros, chaves e backups**.

```powershell
docker compose down -v
docker compose up -d --build
docker compose exec --user www-data app php artisan backups:install
```

---

## 7. Problemas comuns e soluções

### Porta já em uso

Erro `Bind for 127.0.0.1:8190 failed: port is already allocated` (ou 5435): mude `APP_PORT`/`APP_URL` (ou `DB_PORT`) no `.env` e rode `docker compose up -d` de novo.

### O painel diz que o executor está sem contato

O worker não está rodando ou não acessa o banco de controle.

```powershell
docker compose ps
docker compose logs --tail=100 worker
```

Se o worker estiver reiniciando sem parar, confira `DB_DATABASE`, `DB_USERNAME` e `DB_PASSWORD` no `.env` e reinicie com `docker compose up -d`.

### `password authentication failed` no `db`/`app`/`worker` logo após instalar

As credenciais do `.env` foram trocadas depois da criação do volume `pg_data`. Volte às credenciais originais ou, em máquina de teste, [comece do zero](#começar-do-zero-apaga-tudo).

### Erros de backup mais frequentes

O painel já mostra a dica de correção abaixo de cada falha (seção 4.5). Resumo:

| Mensagem | Solução |
|---|---|
| `SSL is required but the server doesn't support it` | Conexão TLS → **Sem TLS / túnel externo** |
| `Access denied for user` | Confira usuário/senha e libere o IP da máquina no acesso remoto da hospedagem |
| `Unknown database` | Confira o nome exato do banco |
| `Can't connect to MySQL server` | Confira host/porta e o acesso remoto liberado |
| `Motores não transacionais: MyISAM` | Consistência → **Bloqueio das tabelas do banco (MyISAM)** |
| Erro de `LOCK TABLES` | Peça à hospedagem a permissão `LOCK TABLES` para o usuário |
| `server version mismatch` (PostgreSQL) | Atualize o `postgresql-client` no `Dockerfile` |

### O painel não mostra as mudanças depois de atualizar o código

Rode `docker compose up -d --build` e recarregue a página com **Ctrl+F5** (limpa o cache do navegador).

### `entrypoint.sh: not found` ou `\r: command not found`

Os arquivos foram convertidos para CRLF. Rode `git config core.autocrlf false`, apague a pasta e clone de novo.

---

## 8. Como o backup funciona por dentro

1. O painel (Vue) envia os cadastros à API Laravel, com sessão e proteção CSRF.
2. O Laravel guarda a senha do banco **criptografada** e grava agendamentos e fila no PostgreSQL de controle.
3. O worker Python verifica a cada 15 s os agendamentos vencidos e a fila.
4. A credencial é entregue ao worker pelo comando local `backups:payload`, via pipe. **Não existe endpoint HTTP que devolva senhas.**
5. O dump (`mysqldump`, `pg_dump` ou `sqlite3 .dump`) é enviado em fluxo para gzip e criptografado na hora com **AES-256-GCM** em blocos. O SQL não é gravado em disco em texto aberto. As senhas não aparecem nos argumentos dos processos.
6. O worker valida a criptografia e o gzip, calcula o SHA-256, faz a cópia externa (se exigida) e registra o resultado.
7. A retenção só é aplicada após um backup bem-sucedido (e da cópia externa, quando habilitada).
8. No download, o arquivo é descriptografado e entregue em ZIP **em fluxo**; nada descriptografado fica salvo no servidor.

Nome do arquivo guardado: `db-<id-do-banco>_<data>_<hora>_job-<id-da-execução>.sql.gz.enc`.

### O que o dump MySQL inclui

Estrutura, dados, views, triggers, procedures, functions e events, **conforme as permissões do usuário**. Não inclui usuários/grants do servidor, binlogs, arquivos do site nem configuração do MySQL. Não faça alterações de estrutura (ALTER/DROP/RENAME/TRUNCATE) durante o backup. O sistema nunca usa `--force` para "fingir" sucesso.

---

## 9. Segurança e chaves

No primeiro início, o container gera automaticamente, uma única vez:

| Arquivo | Para que serve |
|---|---|
| `/data/app.key` | Chave do Laravel. Abre as senhas dos bancos cadastrados |
| `/data/keys/backup.key` | Chave mestra dos arquivos de backup |
| `/data/keys/ssh_known_hosts` | Chaves SSH registradas dos servidores SQLite remotos |

- **Faça cópia segura das duas chaves fora deste servidor**, separada dos backups:
  ```powershell
  docker compose cp app:/data/app.key ./app.key.copia
  docker compose cp app:/data/keys/backup.key ./backup.key.copia
  ```
  Guarde as cópias em local protegido e apague-as da pasta do projeto.
- **Sem a `backup.key`, os backups não podem ser recuperados.** Quem tem a chave consegue abrir os backups.
- **Não rode `php artisan key:generate`** nesta instalação. Se `APP_KEY` for definida no `.env`, ela tem prioridade sobre `/data/app.key`: preserve a que estiver em uso.
- O ZIP baixado contém o banco **aberto**. Guarde-o em local seguro e apague quando não precisar mais.
- **TLS:** use **Exigir TLS** ou **TLS + validar identidade** sempre que o servidor suportar. **Sem TLS** é para servidores que não suportam criptografia ou para redes/túneis confiáveis; nesse caso os dados trafegam sem criptografia entre a máquina e o servidor do banco (o arquivo de backup continua criptografado).
- Certificados CA: coloque o `.pem` em `certs/` e informe só o nome do arquivo no painel. Nunca coloque chaves privadas ou senhas nessa pasta.

---

## 10. Restauração de um backup

**Backup validado não é o mesmo que backup restaurado.** Faça um teste de restauração pelo menos uma vez por mês, num banco separado.

1. No painel, baixe o ZIP da execução desejada e extraia o `.sql`.
2. Crie um **banco vazio de teste** com versão compatível.
3. Importe:
   ```bash
   # MySQL
   mysql -h HOST -u USUARIO -p banco_de_teste < arquivo.sql
   # PostgreSQL
   psql -h HOST -U USUARIO -d banco_de_teste -f arquivo.sql
   # SQLite
   sqlite3 novo_banco.sqlite < arquivo.sql
   ```
4. Confira a quantidade de tabelas e registros críticos, as views e rotinas, e se a aplicação funciona.

O dump MySQL não contém `CREATE DATABASE`/`USE`, para permitir a importação em qualquer banco. Revise `DEFINER` e privilégios antes de importar em outro servidor.

### Restauração manual sem o painel

Se o painel não estiver disponível, mas o volume e a chave existirem:

```powershell
docker compose exec --user www-data worker /opt/worker-venv/bin/python python/worker.py zip --input /data/backups/NOME-DO-ARQUIVO.sql.gz.enc --output /data/tmp/restauracao.zip --name restauracao.sql
docker compose cp worker:/data/tmp/restauracao.zip ./restauracao.zip
docker compose exec --user www-data worker rm /data/tmp/restauracao.zip
```

---

## 11. Retenção, disco e cópia externa

Em **Configurações**:

| Opção | Padrão | Descrição |
|---|---|---|
| Backups mantidos por banco | 4 | Os mais antigos concluídos são apagados (o histórico continua) |
| Tempo máximo do dump | 360 min | Aumente para bancos legados muito grandes |
| Reserva mínima de disco | 1 GB | O backup para se o espaço livre ficar abaixo disso |
| Exigir cópia externa | desligado | Copia cada backup para `/external` e confere o SHA-256 |

Para a cópia externa, monte o destino no host e descomente no serviço `worker` do `docker-compose.yml`:

```yaml
volumes:
  - /mnt/backup-remoto:/external
```

O usuário do container (UID/GID 33) precisa ter permissão de escrita. Rode `docker compose up -d` e só então ative **Exigir cópia externa**. Se a cópia falhar, o backup local é preservado, a execução fica como falha e a retenção não é aplicada.

---

## 12. Colocando em produção

A configuração padrão publica o painel só em `127.0.0.1:8190`, o que serve para testes locais. Para acesso remoto:

1. Coloque um proxy com **HTTPS** (Nginx, Caddy, Traefik) na frente da porta do painel.
2. Ajuste o `.env`:
   ```dotenv
   APP_ENV=production
   APP_DEBUG=false
   APP_URL=https://backup.seudominio.com.br
   SESSION_SECURE_COOKIE=true
   ```
3. Para alertas por e-mail, configure `MAIL_MAILER=smtp`, `MAIL_HOST`, `MAIL_PORT`, `MAIL_USERNAME`, `MAIL_PASSWORD`, `MAIL_FROM_ADDRESS` e `BACKUP_ALERT_EMAIL`. Com `MAIL_MAILER=log`, nenhum e-mail é enviado de verdade.
4. Rode `docker compose up -d --build`.

Recomendações:
- Não exponha `/data`, `.env`, o código-fonte nem a porta do PostgreSQL.
- Monitore de fora a idade do último backup bem-sucedido de cada banco. Se o worker parar por completo, ele não consegue avisar a própria ausência.
- Faça cópia do banco de controle (`pg_dump` do container `db`) e das chaves.
- Agendar terça e sexta deixa uma janela de perda desde a última cópia. Ajuste os dias conforme a criticidade.
