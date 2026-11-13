<?php
use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration {
    public function up(): void {
        Schema::table('sis_database_servers', function (Blueprint $t) {
            $t->string('driver', 10)->default('mysql')->after('name');
        });
        // SQLite não usa host/usuário/senha.
        Schema::table('sis_database_servers', function (Blueprint $t) {
            $t->string('host')->nullable()->change();
            $t->unsignedInteger('port')->nullable()->default(3306)->change();
            $t->string('database_name', 255)->change();
            $t->string('username')->nullable()->change();
            $t->text('db_password')->nullable()->change();
        });
    }

    public function down(): void {
        Schema::table('sis_database_servers', function (Blueprint $t) {
            $t->dropColumn('driver');
        });
    }
};
