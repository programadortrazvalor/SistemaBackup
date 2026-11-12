<?php
namespace App\Models;
use Illuminate\Database\Eloquent\Model;
class BackupSchedule extends Model {
    protected $guarded=['id'];
    protected function casts(): array {return ['weekdays'=>'array','enabled'=>'boolean'];}
    public function databaseServer(){return $this->belongsTo(DatabaseServer::class);}
}
