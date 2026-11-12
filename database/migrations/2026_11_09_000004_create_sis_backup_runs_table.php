<?php
use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

return new class extends Migration {
    public function up(): void {
        Schema::create('sis_backup_runs', function (Blueprint $t) {
            $t->id();
            $t->foreignId('database_server_id')->constrained('sis_database_servers');
            $t->foreignId('backup_schedule_id')->nullable()->constrained('sis_backup_schedules');
            $t->string('scheduled_for')->nullable();
            $t->string('source');
            $t->string('status')->default('queued');
            $t->timestamp('started_at')->nullable();
            $t->timestamp('finished_at')->nullable();
            $t->string('filename')->nullable();
            $t->unsignedBigInteger('size_bytes')->nullable();
            $t->unsignedBigInteger('sql_bytes')->nullable();
            $t->string('sha256', 64)->nullable();
            $t->text('error')->nullable();
            $t->text('details')->nullable();
            $t->timestamps();
            $t->unique(['backup_schedule_id', 'scheduled_for']);
            $t->index(['status', 'id']);
        });
        // Um único trabalho pendente/em execução por banco, inclusive sob concorrência.
        DB::statement("CREATE UNIQUE INDEX sis_one_active_backup_per_database ON sis_backup_runs(database_server_id) WHERE status IN ('queued','running')");
    }

    public function down(): void {
        Schema::dropIfExists('sis_backup_runs');
    }
};
