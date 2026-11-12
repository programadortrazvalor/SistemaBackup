# Instalação rápida — Windows / Docker Desktop

1. Extraia o ZIP e abra PowerShell dentro de `backup-laravel-python-vue`.
2. Execute:

```powershell
Copy-Item .env.example .env
docker compose up -d --build
docker compose exec --user www-data app php artisan backups:install
```

3. Informe nome, e-mail e senha para entrar no painel. Depois informe a senha MySQL.
4. Abra http://localhost:8190.
5. Em Bancos de dados, confira a conexão e clique em Gerar backup de teste.
6. Acompanhe no Histórico. Python processa a fila em segundo plano.

Padrão: terça e sexta, 17h30, Cuiabá. Você pode editar os dias e horários no painel. Horários automáticos: 17:01 a 23:59. Testes manuais: qualquer hora.

O host, banco e usuário enviados já estão cadastrados pelo instalador; a senha não foi gravada no pacote. Conexão externa, TLS e permissões precisam ser validados com seu provedor.

Este sistema usa Laravel no backend, Python no executor e Vue.js no frontend. O banco interno de controle é SQLite; os bancos de origem continuam sendo MySQL.

Leia o README antes de habilitar cópia externa, colocar em produção ou restaurar arquivos. Preserve os volumes e as chaves: não use `docker compose down -v`.
