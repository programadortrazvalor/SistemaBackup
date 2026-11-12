<?php
use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration {
    public function up(): void {
        Schema::create('sis_backup_schedules', function (Blueprint $t) {
            $t->id();
            $t->foreignId('database_server_id')->constrained('sis_database_servers');
            $t->text('weekdays');
            $t->string('start_time', 5);
            $t->boolean('enabled')->default(true);
            $t->timestamps();
        });
    }

    public function down(): void {
        Schema::dropIfExists('sis_backup_schedules');
    }
};
