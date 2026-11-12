<?php
$data = env('BACKUP_DATA_PATH', storage_path('app/backup-data'));
return ['name'=>env('APP_NAME','Backup Manager'),'env'=>env('APP_ENV','production'),'debug'=>(bool)env('APP_DEBUG',false),'url'=>env('APP_URL','http://localhost:8190'),'timezone'=>'UTC','locale'=>env('APP_LOCALE','pt_BR'),'fallback_locale'=>'en','faker_locale'=>'pt_BR','cipher'=>'AES-256-CBC','key'=>env('APP_KEY') ?: (is_file($data.'/app.key') ? trim(file_get_contents($data.'/app.key')) : null),'previous_keys'=>[],'maintenance'=>['driver'=>'file']];
