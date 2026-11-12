<?php
use Illuminate\Support\Facades\{Artisan,DB,Mail};
use App\Models\{User,DatabaseServer,BackupSchedule,BackupRun};
Artisan::command('backups:install',function(){
    if(User::exists() && !$this->confirm('Já existe administrador. Criar ou atualizar outro acesso?',false))return;
    $name=$this->ask('Nome do administrador','Jones');
    $email=$this->ask('E-mail de acesso');if(!filter_var($email,FILTER_VALIDATE_EMAIL)){$this->error('E-mail inválido.');return 1;}
    $pass=$this->secret('Senha do painel (mínimo 12 caracteres)');$confirm=$this->secret('Repita a senha');
    if(strlen((string)$pass)<12 || $pass!==$confirm){$this->error('Senhas diferentes ou senha muito curta.');return 1;}
    User::updateOrCreate(['email'=>$email],['name'=>$name,'password'=>$pass]);
    if(!DatabaseServer::exists()){
        $dbpass=$this->secret('Senha MySQL de dyisencoes01 (Enter para configurar depois)');
        $d=DatabaseServer::create(['name'=>'DY Isenções','host'=>'mysql29-farm15.uni5.net','port'=>3306,'database_name'=>'dyisencoes01','username'=>'dyisencoes01','db_password'=>$dbpass??'','tls_mode'=>'REQUIRED','consistency'=>'transaction','enabled'=>strlen((string)$dbpass)>0]);
        BackupSchedule::create(['database_server_id'=>$d->id,'weekdays'=>[2,5],'start_time'=>'17:30','enabled'=>true]);
    }
    foreach(['retention_count'=>'4','timeout_minutes'=>'360','minimum_free_gb'=>'1','external_copy'=>'0'] as $k=>$v)DB::table('backup_settings')->insertOrIgnore(['key'=>$k,'value'=>$v]);
    $this->info('Instalação pronta. Terça e sexta às 17h30 de Cuiabá. Faça um teste manual.');
})->purpose('Configura administrador e banco inicial sem senha no código');
Artisan::command('backups:payload {run}',function(){
    // Exclusivo do processo local. Não existe endpoint HTTP de credenciais.
    $run=BackupRun::findOrFail((int)$this->argument('run'));$d=$run->databaseServer;
    if($run->status!=='running' || !$d->enabled){$this->error('Execução indisponível.');return 1;}
    $this->line(json_encode(['id'=>$d->id,'name'=>$d->name,'host'=>$d->host,'port'=>$d->port,'database'=>$d->database_name,'username'=>$d->username,'password'=>$d->db_password,'tls_mode'=>$d->tls_mode,'ca_file'=>$d->ca_file,'consistency'=>$d->consistency],JSON_THROW_ON_ERROR));
})->purpose('Entrega credencial em pipe ao worker local');
Artisan::command('backups:notify {run}',function(){
    $to=config('backups.alert_email');if(!$to)return;
    if(!filter_var($to,FILTER_VALIDATE_EMAIL)){$this->error('E-mail inválido.');return 1;}
    $run=BackupRun::findOrFail((int)$this->argument('run'));
    $message='Backup #'.$run->id.' / '.$run->databaseServer->name.' / '.$run->status."\n".($run->error??'Confira o histórico.');
    Mail::raw($message,fn($m)=>$m->to($to)->subject('Backup Manager: falha na execução #'.$run->id));
})->purpose('Envia alerta de falha pelo mailer configurado');
