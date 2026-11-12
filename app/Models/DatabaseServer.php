<?php
namespace App\Models;
use Illuminate\Database\Eloquent\Model;
class DatabaseServer extends Model {
    protected $guarded=['id'];
    protected $hidden=['db_password'];
    protected function casts(): array {return ['db_password'=>'encrypted','enabled'=>'boolean'];}
    public function schedules(){return $this->hasMany(BackupSchedule::class);}
    public function latestRun(){return $this->hasOne(BackupRun::class)->latestOfMany();}
}
