<?php
use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;

return new class extends Migration {
    // Agendamentos passam a acompanhar o estado do banco: banco inativo => agendamento inativo.
    public function up(): void {
        DB::table('sis_backup_schedules')
            ->whereIn('database_server_id', DB::table('sis_database_servers')->where('enabled', false)->select('id'))
            ->update(['enabled' => false]);
    }

    public function down(): void {}
};
