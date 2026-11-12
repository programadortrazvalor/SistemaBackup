<?php
namespace App\Models;
use Illuminate\Database\Eloquent\Model;
class SisBackupSchedule extends Model {
    protected $table='sis_backup_schedules';
    protected $guarded=['id'];
    protected function casts(): array {return ['weekdays'=>'array','enabled'=>'boolean'];}
    public function databaseServer(){return $this->belongsTo(SisDatabaseServer::class,'database_server_id');}
}
