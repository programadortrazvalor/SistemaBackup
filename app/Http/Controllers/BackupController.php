<?php
namespace App\Http\Controllers;
use App\Models\{DatabaseServer,BackupSchedule,BackupRun};
use Illuminate\Http\Request;
use Illuminate\Support\Facades\{DB,Auth};
use Illuminate\Validation\ValidationException;
use Illuminate\Database\QueryException;
class BackupController {
    public function login(Request $r){
        $data=$r->validate(['email'=>'required|email','password'=>'required|string']);
        if(!Auth::attempt($data))throw ValidationException::withMessages(['email'=>'E-mail ou senha inválidos.']);
        $r->session()->regenerate();return response()->json(['user'=>$r->user(),'csrf'=>csrf_token()]);
    }
    public function logout(Request $r){Auth::logout();$r->session()->invalidate();$r->session()->regenerateToken();return response()->json(['csrf'=>csrf_token()]);}
    public function me(Request $r){return ['user'=>$r->user(),'csrf'=>csrf_token()];}
    public function overview(){
        return ['databases'=>DatabaseServer::with('latestRun')->orderBy('name')->get(),'schedules'=>BackupSchedule::with('databaseServer:id,name,enabled')->get(),'runs'=>BackupRun::with('databaseServer:id,name')->latest('id')->limit(100)->get(),'settings'=>$this->settings(),'stats'=>['databases'=>DatabaseServer::count(),'schedules'=>BackupSchedule::where('enabled',true)->whereHas('databaseServer',fn($q)=>$q->where('enabled',true))->count(),'available'=>BackupRun::where('status','success')->count(),'failed'=>BackupRun::where('status','failed')->where('finished_at','>=',now()->subDay())->count()]];
    }
    public function saveDatabase(Request $r,?DatabaseServer $database=null){
        $data=$r->validate(['name'=>'required|string|max:120','host'=>['required','string','max:253','regex:/^[a-zA-Z0-9.:-]+$/D'],'port'=>'required|integer|between:1,65535','database_name'=>['required','string','max:64','regex:/^[a-zA-Z0-9_$-]+$/D'],'username'=>'required|string|max:128','db_password'=>($database?'nullable':'required').'|string|max:4096','tls_mode'=>'required|in:REQUIRED,VERIFY_IDENTITY,DISABLED','ca_file'=>['nullable','string','max:120','regex:/^[a-zA-Z0-9_.-]+$/D'],'consistency'=>'required|in:transaction,locked','enabled'=>'required|boolean']);
        if(($data['db_password']??null)===null || $data['db_password']==='')unset($data['db_password']);
        if(!empty($data['ca_file']) && ($data['ca_file']==='.' || $data['ca_file']==='..'))throw ValidationException::withMessages(['ca_file'=>'Nome de certificado inválido.']);
        $database??=new DatabaseServer();$database->fill($data)->save();return $database->fresh();
    }
    public function saveSchedule(Request $r,?BackupSchedule $schedule=null){
        $data=$r->validate(['database_server_id'=>'required|exists:database_servers,id','weekdays'=>'required|array|min:1|max:7','weekdays.*'=>'required|integer|between:1,7|distinct','start_time'=>['required','date_format:H:i',function($attr,$value,$fail){if($value<='17:00')$fail('Escolha um horário após as 17h, entre 17:01 e 23:59.');}],'enabled'=>'required|boolean']);
        $data['weekdays']=array_map('intval',$data['weekdays']);sort($data['weekdays']);$schedule??=new BackupSchedule();$schedule->fill($data)->save();return $schedule->fresh();
    }
    public function dispatch(DatabaseServer $database){
        abort_unless($database->enabled,422,'Ative o banco antes de executar um teste.');
        try{$run=BackupRun::create(['database_server_id'=>$database->id,'source'=>'manual','status'=>'queued']);}
        catch(QueryException $e){if(BackupRun::where('database_server_id',$database->id)->whereIn('status',['queued','running'])->exists())abort(409,'Este banco já tem um backup na fila ou em execução.');throw $e;}
        return response()->json($run,202);
    }
    public function download(BackupRun $run){
        abort_unless($run->status==='success' && $run->filename,404);
        $path=config('backups.data_path').'/backups/'.basename($run->filename);
        abort_unless(is_file($path),404,'Arquivo expirado ou indisponível.');
        return response()->download($path,basename($path),['Content-Type'=>'application/octet-stream','Cache-Control'=>'no-store']);
    }
    public function settings(): array {
        $settings=DB::table('backup_settings')->pluck('value','key')->all();
        return ['retention_count'=>(int)($settings['retention_count']??4),'timeout_minutes'=>(int)($settings['timeout_minutes']??360),'minimum_free_gb'=>(int)($settings['minimum_free_gb']??1),'external_copy'=>($settings['external_copy']??'0')==='1','worker_heartbeat'=>$settings['worker_heartbeat']??null,'timezone'=>config('backups.timezone')];
    }
    public function saveSettings(Request $r){
        $data=$r->validate(['retention_count'=>'required|integer|between:1,104','timeout_minutes'=>'required|integer|between:1,1440','minimum_free_gb'=>'required|integer|between:1,10000','external_copy'=>'required|boolean']);
        DB::transaction(function()use($data){foreach($data as $key=>$value)DB::table('backup_settings')->updateOrInsert(['key'=>$key],['value'=>is_bool($value)?($value?'1':'0'):(string)$value]);});
        return $this->settings();
    }
}
