<?php
namespace App\Models;
use Illuminate\Database\Eloquent\Model;
class SisDatabaseServer extends Model {
    protected $table='sis_database_servers';
    protected $guarded=['id'];
    protected $hidden=['db_password'];
    protected function casts(): array {return ['db_password'=>'encrypted','enabled'=>'boolean'];}
    public function schedules(){return $this->hasMany(SisBackupSchedule::class,'database_server_id');}
    public function latestRun(){return $this->hasOne(SisBackupRun::class,'database_server_id')->latestOfMany();}
}
