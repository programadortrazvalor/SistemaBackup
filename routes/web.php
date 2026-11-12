<?php
use Illuminate\Support\Facades\Route;
use App\Http\Controllers\SisBackupController;
Route::get('/',fn()=>view('app'))->name('login');
Route::prefix('api')->middleware('throttle:120,1')->group(function(){
    Route::get('/csrf',fn()=>response()->json(['csrf'=>csrf_token()])->header('Cache-Control','no-store'));
    Route::post('/login',[SisBackupController::class,'login'])->middleware('throttle:login');
    Route::middleware('auth')->group(function(){
        Route::get('/me',[SisBackupController::class,'me']);
        Route::post('/logout',[SisBackupController::class,'logout']);
        Route::get('/overview',[SisBackupController::class,'overview']);
        Route::post('/databases',[SisBackupController::class,'saveDatabase']);
        Route::put('/databases/{database}',[SisBackupController::class,'saveDatabase']);
        Route::post('/databases/{database}/backup',[SisBackupController::class,'dispatch']);
        Route::post('/schedules',[SisBackupController::class,'saveSchedule']);
        Route::put('/schedules/{schedule}',[SisBackupController::class,'saveSchedule']);
        Route::get('/runs/{run}/download',[SisBackupController::class,'download']);
        Route::put('/settings',[SisBackupController::class,'saveSettings']);
    });
});
