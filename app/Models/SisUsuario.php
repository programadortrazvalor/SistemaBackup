<?php
namespace App\Models;
use Illuminate\Database\Eloquent\Concerns\HasUuids;
use Illuminate\Foundation\Auth\User as Authenticatable;
class SisUsuario extends Authenticatable {
    use HasUuids;
    protected $table='sis_usuarios';
    protected $fillable=['nome','email','password','celular','cpf','imagem','data_nascimento','idioma','dono_participante','excluir','status'];
    protected $hidden=['password'];
    // sis_usuarios não tem remember_token.
    protected $rememberTokenName='';
    protected function casts(): array {return ['password'=>'hashed','data_nascimento'=>'date'];}
}
