<?php
namespace App\Models;
use Illuminate\Database\Eloquent\Model;
class SisBackupSetting extends Model {
    protected $table='sis_backup_settings';
    protected $primaryKey='key';
    protected $keyType='string';
    public $incrementing=false;
    public $timestamps=false;
    protected $fillable=['key','value'];
}
