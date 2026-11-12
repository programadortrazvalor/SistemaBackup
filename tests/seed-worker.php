<?php
if(getenv('BK_TEST_ISOLATED')!=='yes')exit(1);
require dirname(__DIR__).'/vendor/autoload.php';
$app=require dirname(__DIR__).'/bootstrap/app.php';$app->make(Illuminate\Contracts\Console\Kernel::class)->bootstrap();
App\Models\SisUsuario::create(['nome'=>'QA','email'=>'qa@example.test','password'=>'test-password-123','celular'=>'65999990000','cpf'=>'00000000000','data_nascimento'=>'1990-01-01']);
$d=App\Models\SisDatabaseServer::create(['name'=>'QA','host'=>'localhost','port'=>3306,'database_name'=>'qa','username'=>'test','db_password'=>'dummy-secret-password','tls_mode'=>'REQUIRED','consistency'=>'transaction','enabled'=>true]);
App\Models\SisBackupRun::create(['database_server_id'=>$d->id,'source'=>'manual','status'=>'queued']);
foreach(['retention_count'=>'2','timeout_minutes'=>'1','minimum_free_gb'=>'0','external_copy'=>'0'] as $key=>$value)Illuminate\Support\Facades\DB::table('sis_backup_settings')->insert(['key'=>$key,'value'=>$value]);
