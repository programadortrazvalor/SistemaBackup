<?php
namespace App\Models;
use Illuminate\Database\Eloquent\Model;
class BackupRun extends Model {
    protected $guarded=['id'];
    protected function casts(): array {return ['started_at'=>'datetime','finished_at'=>'datetime','details'=>'array','size_bytes'=>'integer','sql_bytes'=>'integer'];}
    public function databaseServer(){return $this->belongsTo(DatabaseServer::class);}
}
