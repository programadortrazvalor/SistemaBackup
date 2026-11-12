<?php
use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;
use Illuminate\Support\Facades\DB;
return new class extends Migration {
    public function up(): void {
        Schema::create('users',function(Blueprint $t){$t->id();$t->string('name');$t->string('email')->unique();$t->string('password');$t->rememberToken();$t->timestamps();});
        Schema::create('database_servers',function(Blueprint $t){$t->id();$t->string('name');$t->string('host');$t->unsignedInteger('port')->default(3306);$t->string('database_name');$t->string('username');$t->text('db_password');$t->string('tls_mode')->default('REQUIRED');$t->string('ca_file')->nullable();$t->string('consistency')->default('transaction');$t->boolean('enabled')->default(true);$t->timestamps();});
        Schema::create('backup_schedules',function(Blueprint $t){$t->id();$t->foreignId('database_server_id')->constrained();$t->text('weekdays');$t->string('start_time',5);$t->boolean('enabled')->default(true);$t->timestamps();});
        Schema::create('backup_runs',function(Blueprint $t){$t->id();$t->foreignId('database_server_id')->constrained();$t->foreignId('backup_schedule_id')->nullable()->constrained();$t->string('scheduled_for')->nullable();$t->string('source');$t->string('status')->default('queued');$t->timestamp('started_at')->nullable();$t->timestamp('finished_at')->nullable();$t->string('filename')->nullable();$t->unsignedBigInteger('size_bytes')->nullable();$t->unsignedBigInteger('sql_bytes')->nullable();$t->string('sha256',64)->nullable();$t->text('error')->nullable();$t->text('details')->nullable();$t->timestamps();$t->unique(['backup_schedule_id','scheduled_for']);$t->index(['status','id']);});
        // Um único trabalho pendente/em execução por banco, inclusive sob concorrência.
        DB::statement("CREATE UNIQUE INDEX one_active_backup_per_database ON backup_runs(database_server_id) WHERE status IN ('queued','running')");
        Schema::create('backup_settings',function(Blueprint $t){$t->string('key')->primary();$t->text('value');});
    }
    public function down(): void {foreach(['backup_settings','backup_runs','backup_schedules','database_servers','users'] as $t)Schema::dropIfExists($t);}
};
