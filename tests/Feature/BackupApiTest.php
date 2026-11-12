<?php
namespace Tests\Feature;
use Tests\TestCase;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\DB;
use App\Models\{User,DatabaseServer,BackupRun};
class BackupApiTest extends TestCase {
    use RefreshDatabase;
    private function admin(): User{return User::create(['name'=>'Jones','email'=>'qa@example.test','password'=>'only-a-test-password']);}
    private function database(): DatabaseServer{return DatabaseServer::create(['name'=>'QA','host'=>'127.0.0.1','port'=>3306,'database_name'=>'qa','username'=>'qa','db_password'=>'only-a-db-test-secret','tls_mode'=>'REQUIRED','consistency'=>'transaction','enabled'=>true]);}
    public function test_api_requires_authentication():void{$this->getJson('/api/overview')->assertUnauthorized();}
    public function test_login_and_logout():void{
        $this->admin();$this->postJson('/api/login',['email'=>'qa@example.test','password'=>'wrong'])->assertUnprocessable();
        $this->postJson('/api/login',['email'=>'qa@example.test','password'=>'only-a-test-password'])->assertOk()->assertJsonStructure(['user','csrf']);
        $this->getJson('/api/me')->assertOk();$this->postJson('/api/logout')->assertOk();$this->assertGuest();
    }
    public function test_credentials_are_encrypted_and_hidden():void{
        $this->actingAs($this->admin());$d=$this->database();
        $stored=DB::table('database_servers')->value('db_password');$this->assertNotEquals('only-a-db-test-secret',$stored);$this->assertSame('only-a-db-test-secret',$d->fresh()->db_password);
        $response=$this->getJson('/api/overview')->assertOk();$this->assertStringNotContainsString('only-a-db-test-secret',$response->getContent());$this->assertArrayNotHasKey('db_password',$response->json('databases.0'));
    }
    public function test_schedule_rejects_17h_and_accepts_17h01():void{
        $this->actingAs($this->admin());$d=$this->database();$base=['database_server_id'=>$d->id,'weekdays'=>['2','5'],'enabled'=>true];
        foreach(['16:59','17:00','24:00'] as $time)$this->postJson('/api/schedules',$base+['start_time'=>$time])->assertUnprocessable();
        $this->postJson('/api/schedules',$base+['start_time'=>'17:01'])->assertOk();$this->assertDatabaseCount('backup_schedules',1);$this->assertSame([2,5],\App\Models\BackupSchedule::first()->weekdays);
    }
    public function test_schedule_rejects_invalid_days():void{
        $this->actingAs($this->admin());$d=$this->database();
        $this->postJson('/api/schedules',['database_server_id'=>$d->id,'weekdays'=>[0,8],'start_time'=>'17:30','enabled'=>true])->assertUnprocessable();
    }
    public function test_manual_queue_is_unique_per_database():void{
        $this->actingAs($this->admin());$d=$this->database();
        $this->postJson('/api/databases/'.$d->id.'/backup')->assertAccepted();$this->postJson('/api/databases/'.$d->id.'/backup')->assertConflict();$this->assertDatabaseCount('backup_runs',1);
    }
    public function test_paused_database_cannot_queue_backup():void{
        $this->actingAs($this->admin());$d=$this->database();$d->update(['enabled'=>false]);$this->postJson('/api/databases/'.$d->id.'/backup')->assertUnprocessable();
    }
    public function test_blank_password_on_edit_preserves_secret():void{
        $this->actingAs($this->admin());$d=$this->database();$body=$d->toArray();$body['db_password']='';$body['name']='Updated';
        $this->putJson('/api/databases/'.$d->id,$body)->assertOk();$this->assertSame('only-a-db-test-secret',$d->fresh()->db_password);
    }
    public function test_settings_validation_and_persistence():void{
        $this->actingAs($this->admin());$this->putJson('/api/settings',['retention_count'=>0])->assertUnprocessable();
        $this->putJson('/api/settings',['retention_count'=>6,'timeout_minutes'=>60,'minimum_free_gb'=>2,'external_copy'=>true])->assertOk()->assertJsonPath('external_copy',true);
    }
    public function test_missing_or_expired_download_is_not_available():void{
        $this->actingAs($this->admin());$d=$this->database();$run=BackupRun::create(['database_server_id'=>$d->id,'source'=>'manual','status'=>'expired','filename'=>'unavailable.enc']);$this->get('/api/runs/'.$run->id.'/download')->assertNotFound();
    }
}
