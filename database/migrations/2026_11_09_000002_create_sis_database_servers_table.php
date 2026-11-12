<?php
use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration {
    public function up(): void {
        Schema::create('sis_database_servers', function (Blueprint $t) {
            $t->id();
            $t->string('name');
            $t->string('host');
            $t->unsignedInteger('port')->default(3306);
            $t->string('database_name');
            $t->string('username');
            $t->text('db_password');
            $t->string('tls_mode')->default('REQUIRED');
            $t->string('ca_file')->nullable();
            $t->string('consistency')->default('transaction');
            $t->boolean('enabled')->default(true);
            $t->timestamps();
        });
    }

    public function down(): void {
        Schema::dropIfExists('sis_database_servers');
    }
};
