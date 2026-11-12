<?php
return ['default'=>'sqlite','connections'=>['sqlite'=>['driver'=>'sqlite','url'=>env('DB_URL'),'database'=>env('DB_DATABASE',storage_path('app/backup-data/control.sqlite')),'prefix'=>'','foreign_key_constraints'=>true,'busy_timeout'=>10000,'journal_mode'=>'WAL','synchronous'=>'NORMAL']], 'migrations'=>['table'=>'migrations','update_date_on_publish'=>true]];
