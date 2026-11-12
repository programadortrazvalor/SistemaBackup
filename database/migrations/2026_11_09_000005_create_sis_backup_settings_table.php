<?php
use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration {
    public function up(): void {
        Schema::create('sis_backup_settings', function (Blueprint $t) {
            $t->string('key')->primary();
            $t->text('value');
        });
    }

    public function down(): void {
        Schema::dropIfExists('sis_backup_settings');
    }
};
