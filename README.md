# Backup Manager — Laravel + Python + Vue.js

Sistema completo de controle e execução de backups de bancos MySQL remotos.

| Parte | Tecnologia | Função |
|---|---|---|
| Backend e API | Laravel 12 / PHP 8.3 | Login, cadastros, regras, fila, histórico e downloads |
| Execução | Python 3.12 | Agendamento, mysqldump, compressão, criptografia e retenção |
| Frontend | Vue 3 / Vite | Painel, formulários e atualização do histórico |
| Controle interno | SQLite em volume persistente | Metadados e fila compartilhados entre Laravel e Python |
| Bancos de origem | MySQL | Bancos que serão copiados, sem alteração de seus dados |

Esta entrega substitui o projeto anterior em PHP puro. É uma instalação nova; os formatos de arquivo/chaves do pacote anterior não são intercambiáveis com esta versão.

## Início rápido — Windows com Docker Desktop

Extraia o ZIP e entre na pasta `backup-laravel-python-vue` pelo PowerShell:

```powershell
Copy-Item .env.example .env
docker compose up -d --build
docker compose exec --user www-data app php artisan backups:install
```

Abra **http://localhost:8190**.

O comando de instalação solicita nome, e-mail e senha do administrador e senha do MySQL. A senha do painel exige pelo menos 12 caracteres e confirmação.

O banco inicial já usa:

- Nome: DY Isenções
- Host: `mysql29-farm15.uni5.net`
- Porta: `3306`
- Usuário e banco: `dyisencoes01`
- Dias: **terça e sexta**
- Horário: **17h30 de Cuiabá**

A senha informada na conversa **não está no código nem no ZIP**. Digite-a na instalação ou no cadastro do banco. Se a senha MySQL ficar vazia na instalação, o banco começa pausado.

Docker instala Composer, dependências PHP, Python, cliente MySQL, Nginx e o build Vue. Não precisa ter PHP/Python/Node instalados no Windows para essa opção. A primeira construção precisa de acesso aos repositórios de pacotes e imagens.

### Linux com Docker

```bash
cp .env.example .env
docker compose up -d --build
docker compose exec --user www-data app php artisan backups:install
```

## Como os backups funcionam

1. O Vue envia as alterações à API Laravel, com sessão e proteção CSRF.
2. Laravel criptografa a senha do banco e grava os agendamentos no banco de controle.
3. Python consulta os agendamentos a cada 15 segundos e coloca as ocorrências devidas na fila.
4. O worker solicita a credencial ao comando local `backups:payload`, por pipe. Não existe endpoint HTTP que devolva senhas.
5. `mysqldump` envia o SQL em fluxo para gzip; os bytes comprimidos são imediatamente criptografados com AES-256-GCM em blocos. O SQL completo não é carregado na RAM nem gravado em disco em texto aberto.
6. O worker valida autenticação criptográfica e gzip, calcula SHA-256, envia a cópia externa se exigida e registra o resultado.
7. A retenção só é aplicada após um backup bem-sucedido e sua cópia externa, quando habilitada.

Os arquivos recebem nome com ID do banco, data/hora de Cuiabá e ID da execução: `db-1_2026-11-10_17-30-00_job-12.sql.gz.enc`.

## Agendamentos e testes

- No painel **Agendamentos**, adicione quantas rotinas precisar: banco, dias e horário.
- Tanto o Vue quanto o Laravel validam horários **entre 17:01 e 23:59**.
- O fuso usado é **America/Cuiaba**, independentemente do fuso do host.
- **Gerar backup de teste** enfileira uma execução manual a qualquer hora. O Python inicia quando a fila permitir.
- O histórico atualiza a cada 10 segundos. Não é necessário deixar o painel aberto.
- Um único worker tem o lock de execução; um índice único no banco impede trabalhos ativos duplicados para a mesma origem.
- Os bancos são processados sequencialmente. O horário configurado é o início previsto, não garantia de início pontual se outro banco estiver em execução.
- Um agendamento perdido pode ser recuperado até 6 horas após seu horário, no mesmo dia. Uma ocorrência pendente que perdeu essa janela é cancelada, sem execução automática pela manhã.
- Uma execução interrompida vira falha no próximo início do worker. Depois de verificar a causa, solicite novo teste.
- Pausar banco ou agendamento cancela trabalhos pendentes; não interrompe um dump que já começou.

**Não configure cron ao usar o serviço `worker` do Docker.** Ele já mantém o processo em segundo plano. Para conferir:

```powershell
docker compose ps
docker compose logs --tail=100 worker
```

Se o primeiro comando de instalação informar que o serviço ainda não está rodando, aguarde o build/início terminar e confira os logs de `app`.

## Primeiro backup real

1. Faça login com o acesso criado no instalador.
2. Em **Bancos de dados**, confira usuário, senha, TLS e modo de consistência.
3. Autorize o IP público da máquina executora no provedor MySQL, se exigido.
4. Clique em **Gerar backup de teste**.
5. Aguarde a conclusão no histórico e confira tamanho, duração, checksum e detalhes.
6. Baixe o arquivo e faça a restauração de teste descrita abaixo.

Os testes desta entrega usam clientes MySQL simulados; não foi feita conexão ou cópia no banco real informado.

## Segurança e consistência

### TLS

O padrão é **REQUIRED**, que exige criptografia da conexão. Para verificar também o certificado e o nome do servidor, selecione **VERIFY_IDENTITY**, preferencialmente com CA do provedor.

Se necessário, coloque o certificado CA em `certs/ca.pem` e cadastre apenas `ca.pem` no painel. A pasta é montada somente leitura em `/certs` nos dois serviços. Não coloque chave privada nessa pasta.

`DISABLED` é uma opção explícita para rede confiável/túnel administrado. Não há fallback automático para conexão sem TLS.

### Bancos legados

Antes de gerar o dump, Python identifica os motores de tabelas do banco:

- **Transação InnoDB:** usa `--single-transaction --quick`. Se detectar MyISAM/MEMORY/outros motores não transacionais, falha com uma mensagem explicativa.
- **Bloqueio global:** usa `--lock-all-tables`, exige privilégios e pode impedir escritas em toda a instância durante o backup. Use somente numa janela de manutenção combinada com o provedor.

Não faça migrações ALTER/CREATE/DROP/RENAME/TRUNCATE durante o backup InnoDB. O sistema não ignora erros do dump nem usa `--force` para fingir conclusão.

O dump inclui estrutura, dados, views, triggers, procedures, functions e events **conforme os privilégios concedidos ao usuário**. Se não houver permissão, a execução pode falhar; confira com o provedor.

É um backup de um banco de aplicação, não uma imagem da instância. Não inclui binlogs, usuários/grants globais do servidor, arquivos enviados ao site ou configuração do MySQL. Bancos distintos não compartilham um snapshot transacional.

### Chaves

O container gera automaticamente, uma única vez:

- `/data/app.key`: chave Laravel, usada para abrir as credenciais.
- `/data/keys/backup.key`: chave mestra dos arquivos criptografados.

**Não execute `php artisan key:generate` nesta instalação Docker.** A chave compartilhada já é criada e persistida no volume. Uma mudança sem plano de rotação pode impedir o acesso às credenciais.

Faça uma cópia segura das duas chaves fora do servidor, separada dos backups. Quem possui a chave de backup pode descriptografar os arquivos; quem perde a chave não consegue recuperá-los. `APP_KEY`, quando definida explicitamente, tem precedência sobre `/data/app.key`: preserve a chave que de fato estiver em uso.

O worker usa um arquivo temporário de opções MySQL com permissão 0600, removido ao finalizar; a senha não aparece nos argumentos do processo. Temporários deixados por interrupção abrupta são removidos no próximo início do worker.

## Retenção, disco e cópia externa

Em **Configurações**, ajuste:

- Quantidade de backups mantidos por banco (padrão 4).
- Tempo máximo do processo de dump (padrão 360 minutos). Consultas iniciais, validação final e envio externo são etapas adicionais.
- Reserva mínima de espaço (padrão 1 GB).
- Exigência de cópia externa.

Dimensione espaço a partir do primeiro backup medido. A compressão depende dos dados; o sistema não promete tamanho ou duração fixos. O dump é gerado diretamente no arquivo comprimido/criptografado para reduzir uso de memória e disco temporário.

Para cópia externa, primeiro configure um volume remoto no host, como um armazenamento montado em `/mnt/backup-remoto`. Descomente e ajuste no serviço `worker` do Compose:

```yaml
volumes:
  - /mnt/backup-remoto:/external
```

O usuário do worker (UID/GID 33) precisa conseguir escrever nesse destino. Reinicie os serviços após alterar o Compose e só então ative **Exigir cópia externa** no painel. O sistema não configura S3/SFTP/montagem remota por conta própria.

A cópia é escrita como `.partial`, tem SHA-256 conferido e só então recebe o nome final. Se falhar, o arquivo local completo é preservado em `/data/backups` e a execução fica como falha, sem aplicar retenção. Esse arquivo pode ser localizado pelo ID da execução no nome, mesmo que o painel não ofereça download daquela falha. Verifique capacidade e conectividade antes de repetir.

Retenção remove arquivos locais e cópias externas dos backups expirados; o histórico permanece. Configurações novas valem para as próximas execuções.

## Recuperação e teste de restauração

**Backup validado por gzip/criptografia não equivale a SQL restaurado.** Faça restauração pelo menos mensalmente, em banco separado e versão MySQL compatível.

Liste os arquivos:

```powershell
docker compose exec --user www-data worker ls -lh /data/backups
```

Substitua `NOME-DO-ARQUIVO` pelo arquivo real:

```powershell
docker compose exec --user www-data worker /opt/worker-venv/bin/python python/worker.py decrypt --input /data/backups/NOME-DO-ARQUIVO.sql.gz.enc --output /data/tmp/restauracao.sql.gz
docker compose exec --user www-data worker gzip -t /data/tmp/restauracao.sql.gz
docker compose cp worker:/data/tmp/restauracao.sql.gz ./restauracao.sql.gz
```

A saída precisa ser um arquivo novo: o descriptografador não sobrescreve. Se a autenticação falhar, apaga a saída parcial.

O dump não inclui CREATE DATABASE/USE, para permitir a importação em outro banco. Crie um banco vazio de teste, mantenha seus eventos desativados, revise DEFINER/privilégios e importe com cliente MySQL compatível. Exemplo em Linux, com um arquivo de credenciais de restauração 0600 já configurado:

```bash
bash -o pipefail -c 'gzip -dc restauracao.sql.gz | mysql --defaults-extra-file=/caminho/restore-client.cnf banco_de_teste'
```

Confira o código de saída, contagens de tabelas/registros críticos, views, rotinas e comportamento da aplicação. Só depois planeje uma eventual restauração em produção. Remova a cópia descriptografada quando terminar.

## Alertas e manutenção

- O painel mostra quando o worker está sem contato recente. A atualização de heartbeat acontece durante o dump e a validação.
- Falhas são registradas no histórico com mensagem e horários.
- Para alertar por e-mail, configure `BACKUP_ALERT_EMAIL` e o mailer SMTP do Laravel em `.env`, depois recrie os serviços. O padrão `MAIL_MAILER=log` apenas registra o envio, não manda e-mail real.
- Se o worker parar por completo, ele não consegue enviar alerta da própria ausência. Monitore a saúde e a idade do último backup bem-sucedido por banco externamente.
- Faça cópia segura do banco de controle e das chaves. Para copiar o SQLite de forma consistente, pare os serviços/coloque em manutenção ou use a API de backup SQLite.
- Os dados persistem no volume `backup_data`. **Não execute `docker compose down -v`**, pois isso apaga volumes, chaves e backups.
- Docker tem rotação dos logs de container configurada. Configure rotação do arquivo Laravel `storage/logs/laravel.log` conforme o servidor.
- Terça/sexta deixa uma janela de perda desde a última cópia. Arquivamento de binlogs para recuperação ponto a ponto não está implementado nesta entrega.

Para redefinir/criar acesso administrativo:

```powershell
docker compose exec --user www-data app php artisan backups:install
```

O comando confirma antes de alterar uma instalação já existente e não recria chaves/bancos existentes.

## Produção

A configuração inicial publica apenas em `127.0.0.1:8190`, adequada ao teste local. Para acesso remoto, coloque um proxy com HTTPS na frente do serviço e configure:

```dotenv
APP_ENV=production
APP_DEBUG=false
APP_URL=https://backup.seudominio.com.br
SESSION_SECURE_COOKIE=true
```

Não exponha `/data`, o código-fonte, `.env` ou certificados privados pela web. O Nginx incluído serve apenas `public`. Mantenha autenticação, firewall e acesso administrativo restritos.

O Docker usa o cliente Oracle MySQL 8.0 fornecido pelo Ubuntu 24.04. Confira compatibilidade com a versão exata do MySQL remoto antes de aprovar o primeiro backup. Se necessário, ajuste a imagem para um cliente Oracle compatível; o worker não usa cliente MariaDB como substituto.

## Desenvolvimento sem Docker

Requer Linux/WSL, PHP 8.3 com extensões Laravel e SQLite, Composer, Node 22+, Python 3.12 com cryptography, cliente Oracle MySQL e acesso a cron/systemd.

Use caminhos locais absolutos em `.env`: `BACKUP_DATA_PATH` e `DB_DATABASE`. Crie os diretórios `keys`, `tmp` e `backups` dentro do diretório de dados. Execute `docker/provision.py` com o mesmo BACKUP_DATA_PATH para criar as chaves e o SQLite, depois:

```bash
composer install
php artisan migrate
php artisan backups:install
npm ci
npm run build
python3 -m venv .venv
.venv/bin/pip install -r python/requirements.txt
php artisan serve --host=127.0.0.1 --port=8190
```

Inicie Python em outro terminal, com o ambiente exportado (ele não carrega `.env` automaticamente):

```bash
BACKUP_DATA_PATH=/caminho/dados BACKUP_APP_PATH=/caminho/projeto PHP_BIN=/usr/bin/php .venv/bin/python python/worker.py
```

Use `--once` para uma execução única da fila/agendamentos. Pode ser chamado por cron a cada minuto, em lugar do daemon, sempre com os mesmos caminhos, usuário e ambiente. O lock impede concorrência. Não execute workers no Windows nativo: utilizam recursos POSIX; use Docker ou WSL.

## Testes da entrega

```bash
composer test
python3 -m unittest discover -s python/tests -v
PHP_BIN=/usr/bin/php python3 python/tests/integration_laravel.py
npm run build
```

O teste de integração cria banco de controle/chaves temporários, usa Laravel real, servidor HTTP local e clientes MySQL simulados. Não usa credenciais reais nem faz conexão no banco do usuário.

- API Laravel: login, autorização, segredo criptografado/oculto, horários/dias, fila duplicada, banco pausado, edição e configurações.
- Python: criptografia em blocos, gzip, adulteração, arquivo truncado, falhas de dump, MyISAM, limpeza e cópia externa/checksum.
- Integração: Laravel abre credencial em pipe, Python executa backup simulado, histórico e download autenticado; valida CSRF e sessão por HTTP real.

O build Docker e a restauração SQL real precisam ser validados no ambiente de instalação; não foram executados nesta sessão.
