<?php
namespace App\Http\Controllers;
use App\Models\{SisDatabaseServer,SisBackupSchedule,SisBackupRun,SisBackupSetting};
use Illuminate\Http\Request;
use Illuminate\Support\Facades\{DB,Auth};
use Illuminate\Validation\ValidationException;
use Illuminate\Database\QueryException;
class SisBackupController {
    public function login(Request $r){
        $data=$r->validate(['email'=>'required|email','password'=>'required|string']);
        if(!Auth::attempt($data))throw ValidationException::withMessages(['email'=>'E-mail ou senha inválidos.']);
        $r->session()->regenerate();return response()->json(['user'=>$r->user(),'csrf'=>csrf_token()]);
    }
    public function logout(Request $r){Auth::logout();$r->session()->invalidate();$r->session()->regenerateToken();return response()->json(['csrf'=>csrf_token()]);}
    public function me(Request $r){return ['user'=>$r->user(),'csrf'=>csrf_token()];}
    public function overview(){
        return ['databases'=>SisDatabaseServer::with('latestRun')->orderBy('name')->get(),'schedules'=>SisBackupSchedule::with('databaseServer:id,name,enabled')->get(),'runs'=>SisBackupRun::with('databaseServer:id,name')->latest('id')->limit(100)->get(),'settings'=>$this->settings(),'stats'=>['databases'=>SisDatabaseServer::count(),'schedules'=>SisBackupSchedule::where('enabled',true)->whereHas('databaseServer',fn($q)=>$q->where('enabled',true))->count(),'available'=>SisBackupRun::where('status','success')->count(),'failed'=>SisBackupRun::where('status','failed')->where('finished_at','>=',now()->subDay())->count()]];
    }
    public function saveDatabase(Request $r,?SisDatabaseServer $database=null){
        $driver=$r->validate(['driver'=>'nullable|in:mysql,pgsql,sqlite'])['driver']??($database?->driver??'mysql');
        $hasPassword=$database && (string)$database->db_password!=='';
        $common=['name'=>'required|string|max:120','tls_mode'=>'required|in:REQUIRED,VERIFY_IDENTITY,DISABLED','ca_file'=>['nullable','string','max:120','regex:/^[a-zA-Z0-9_.-]+$/D'],'consistency'=>'required|in:transaction,tables,locked','enabled'=>'required|boolean'];
        $host=['string','max:253','regex:/^[a-zA-Z0-9.:-]+$/D'];
        if($driver==='sqlite'){
            // Com host: baixa por SFTP/SSH o caminho remoto informado. Sem host: arquivo dentro do volume /sqlite, sem subpastas.
            $remote=trim((string)$r->input('host'))!=='';
            $data=$r->validate(['tls_mode'=>'nullable|in:REQUIRED,VERIFY_IDENTITY,DISABLED','consistency'=>'nullable|in:transaction,tables,locked']+$common+['host'=>['nullable',...$host],'port'=>($remote?'required':'nullable').'|integer|between:1,65535','username'=>($remote?'required':'nullable').'|string|max:128','db_password'=>($remote && !$hasPassword?'required':'nullable').'|string|max:4096',
                'database_name'=>$remote?['required','string','max:255','regex:/^[a-zA-Z0-9_.\/~-]+$/D','not_regex:/(^|\/)\.\.(\/|$)/','not_regex:/\/$/']:['required','string','max:120','regex:/^[a-zA-Z0-9_.-]+$/D','not_in:.,..']]);
            $data['consistency']='transaction';$data['tls_mode']??='DISABLED';
        }else{
            $data=$r->validate($common+['host'=>['required',...$host],'port'=>'required|integer|between:1,65535','database_name'=>['required','string','max:64','regex:/^[a-zA-Z0-9_$-]+$/D'],'username'=>'required|string|max:128','db_password'=>($hasPassword?'nullable':'required').'|string|max:4096']);
            if($driver==='pgsql')$data['consistency']='transaction';
        }
        if(($data['db_password']??null)===null || $data['db_password']==='')unset($data['db_password']);
        if(!empty($data['ca_file']) && ($data['ca_file']==='.' || $data['ca_file']==='..'))throw ValidationException::withMessages(['ca_file'=>'Nome de certificado inválido.']);
        $data['driver']=$driver;
        $database??=new SisDatabaseServer();
        DB::transaction(function()use($database,$data){
            $database->fill($data);$changed=$database->exists && $database->isDirty('enabled');$database->save();
            // Agendamentos acompanham o estado do banco: pausar o banco pausa as rotinas; reativar reativa.
            if($changed)$database->schedules()->update(['enabled'=>$database->enabled]);
        });
        return $database->fresh();
    }
    public function saveSchedule(Request $r,?SisBackupSchedule $schedule=null){
        $data=$r->validate(['database_server_id'=>'required|exists:sis_database_servers,id','weekdays'=>'required|array|min:1|max:7','weekdays.*'=>'required|integer|between:1,7|distinct','start_time'=>['required','date_format:H:i',function($attr,$value,$fail){if($value<='17:00')$fail('Escolha um horário após as 17h, entre 17:01 e 23:59.');}],'enabled'=>'required|boolean']);
        if($data['enabled'] && !SisDatabaseServer::whereKey($data['database_server_id'])->value('enabled'))
            throw ValidationException::withMessages(['enabled'=>'Este banco está inativo. Ative o banco em "Bancos de dados" para ativar o agendamento, ou salve o agendamento desativado.']);
        $data['weekdays']=array_map('intval',$data['weekdays']);sort($data['weekdays']);$schedule??=new SisBackupSchedule();$schedule->fill($data)->save();return $schedule->fresh();
    }
    public function dispatch(SisDatabaseServer $database){
        abort_unless($database->enabled,422,'Ative o banco antes de executar um teste.');
        try{$run=SisBackupRun::create(['database_server_id'=>$database->id,'source'=>'manual','status'=>'queued']);}
        catch(QueryException $e){if(SisBackupRun::where('database_server_id',$database->id)->whereIn('status',['queued','running'])->exists())abort(409,'Este banco já tem um backup na fila ou em execução.');throw $e;}
        return response()->json($run,202);
    }
    public function download(SisBackupRun $run){
        abort_unless($run->status==='success' && $run->filename,404);
        $path=config('backups.data_path').'/backups/'.basename($run->filename);
        abort_unless(is_file($path),404,'Arquivo expirado ou indisponível.');
        // Entrega um .zip com o .sql descriptografado dentro. O arquivo guardado no servidor continua criptografado.
        $base=preg_replace('/\.sql\.gz\.enc$/','',basename($path));
        $label=\Illuminate\Support\Str::slug($run->databaseServer?->name ?? 'banco','_') ?: 'banco';
        $base=preg_replace('/^db-\d+/',$label,$base);
        // O ZIP é gerado em fluxo e enviado enquanto é produzido: sem limite de tempo nem arquivo temporário,
        // então bancos legados que levam horas para baixar não são interrompidos.
        $cmd=[env('WORKER_PYTHON','/opt/worker-venv/bin/python'),base_path('python/worker.py'),'zip','--input='.$path,'--output=-','--name='.$base.'.sql'];
        $process=proc_open($cmd,[0=>['file','/dev/null','r'],1=>['pipe','w'],2=>['file','/dev/null','w']],$pipes,base_path(),['BACKUP_DATA_PATH'=>config('backups.data_path')]+getenv());
        abort_unless(is_resource($process),500,'Não foi possível iniciar a geração do ZIP.');
        // Lê o primeiro bloco antes de responder: se a chave estiver errada, devolve erro em vez de um ZIP vazio.
        $first=fread($pipes[1],65536);
        if($first===false || $first===''){fclose($pipes[1]);proc_close($process);abort(500,'Não foi possível gerar o ZIP do backup. Confira a chave de backup.');}
        return response()->stream(function()use($process,$pipes,$first){
            @set_time_limit(0);
            while(ob_get_level()>0)ob_end_flush();
            echo $first;flush();
            try{
                while(!feof($pipes[1])){
                    $chunk=fread($pipes[1],1048576);
                    if($chunk===false)break;
                    if($chunk!==''){echo $chunk;flush();}
                    if(connection_aborted())break;
                }
            }finally{
                fclose($pipes[1]);
                if(proc_get_status($process)['running'])proc_terminate($process);
                proc_close($process);
            }
        },200,['Content-Type'=>'application/zip','Content-Disposition'=>'attachment; filename="'.$base.'.zip"','Cache-Control'=>'no-store','X-Accel-Buffering'=>'no']);
    }
    public function settings(): array {
        $settings=SisBackupSetting::query()->pluck('value','key')->all();
        return ['retention_count'=>(int)($settings['retention_count']??4),'timeout_minutes'=>(int)($settings['timeout_minutes']??360),'minimum_free_gb'=>(int)($settings['minimum_free_gb']??1),'external_copy'=>($settings['external_copy']??'0')==='1','worker_heartbeat'=>$settings['worker_heartbeat']??null,'timezone'=>config('backups.timezone')];
    }
    public function saveSettings(Request $r){
        $data=$r->validate(['retention_count'=>'required|integer|between:1,104','timeout_minutes'=>'required|integer|between:1,1440','minimum_free_gb'=>'required|integer|between:1,10000','external_copy'=>'required|boolean']);
        DB::transaction(function()use($data){foreach($data as $key=>$value)SisBackupSetting::query()->updateOrInsert(['key'=>$key],['value'=>is_bool($value)?($value?'1':'0'):(string)$value]);});
        return $this->settings();
    }
}
