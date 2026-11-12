<?php
use Illuminate\Support\Facades\Route;
use App\Http\Controllers\BackupController;
Route::get('/',fn()=>view('app'))->name('login');
Route::prefix('api')->middleware('throttle:120,1')->group(function(){
    Route::get('/csrf',fn()=>response()->json(['csrf'=>csrf_token()])->header('Cache-Control','no-store'));
    Route::post('/login',[BackupController::class,'login'])->middleware('throttle:login');
    Route::middleware('auth')->group(function(){
        Route::get('/me',[BackupController::class,'me']);
        Route::post('/logout',[BackupController::class,'logout']);
        Route::get('/overview',[BackupController::class,'overview']);
        Route::post('/databases',[BackupController::class,'saveDatabase']);
        Route::put('/databases/{database}',[BackupController::class,'saveDatabase']);
        Route::post('/databases/{database}/backup',[BackupController::class,'dispatch']);
        Route::post('/schedules',[BackupController::class,'saveSchedule']);
        Route::put('/schedules/{schedule}',[BackupController::class,'saveSchedule']);
        Route::get('/runs/{run}/download',[BackupController::class,'download']);
        Route::put('/settings',[BackupController::class,'saveSettings']);
    });
});
