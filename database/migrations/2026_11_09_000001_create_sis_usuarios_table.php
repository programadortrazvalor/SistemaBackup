<?php
use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

// Cópia da estrutura de ezway.public.sis_users (mesmos tipos, defaults, CHECK e UNIQUE).
return new class extends Migration {
    public function up(): void {
        Schema::create('sis_usuarios', function (Blueprint $t) {
            $t->uuid('id')->primary();
            $t->string('nome', 255);
            $t->string('email', 255)->unique();
            $t->string('password', 255);
            $t->char('celular', 255)->unique();
            $t->char('cpf', 255)->unique();
            $t->string('imagem', 255)->nullable();
            $t->date('data_nascimento')->unique();
            $t->char('idioma', 1)->default('N');
            $t->string('dono_participante', 255)->default('N');
            $t->char('excluir', 1)->default('N');
            $t->char('status', 1)->default('B');
            $t->timestamps();
        });
        DB::statement("ALTER TABLE sis_usuarios ADD CONSTRAINT sis_usuarios_dono_participante_check CHECK (dono_participante IN ('S','N'))");
    }

    public function down(): void {
        Schema::dropIfExists('sis_usuarios');
    }
};
