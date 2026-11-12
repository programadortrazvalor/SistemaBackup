#!/usr/bin/env python3
"""Testa Laravel real + Python + clientes MySQL simulados + API HTTP/CSRF."""
import http.cookiejar,json,os,pathlib,re,socket,sqlite3,subprocess,sys,tempfile,time,urllib.request,urllib.parse
ROOT=pathlib.Path(__file__).resolve().parents[2]
PHP=os.environ.get('PHP_BIN','php')
with tempfile.TemporaryDirectory(prefix='laravel-python-qa-') as tmp:
 data=pathlib.Path(tmp)
 for d in ('tmp','backups','keys'):(data/d).mkdir()
 (data/'keys/backup.key').write_bytes(os.urandom(32));(data/'control.sqlite').touch()
 env=dict(os.environ,APP_ENV='testing',APP_DEBUG='false',APP_KEY='base64:ERERERERERERERERERERERERERERERERERERERERERE=',DB_DATABASE=str(data/'control.sqlite'),BACKUP_DATA_PATH=str(data),BACKUP_APP_PATH=str(ROOT),PHP_BIN=PHP,MYSQL_BIN=str(ROOT/'python/tests/fake-mysql.py'),MYSQLDUMP_BIN=str(ROOT/'python/tests/fake-mysqldump.py'),BK_TEST_ISOLATED='yes',SESSION_SECURE_COOKIE='false',CACHE_STORE='array',BK_TEST_MODE='ok')
 subprocess.run([PHP,str(ROOT/'artisan'),'migrate','--force','--no-ansi'],cwd=ROOT,env=env,check=True,capture_output=True)
 subprocess.run([PHP,str(ROOT/'tests/seed-worker.php')],cwd=ROOT,env=env,check=True,capture_output=True)
 subprocess.run([sys.executable,str(ROOT/'python/worker.py'),'--once'],cwd=ROOT,env=env,check=True)
 con=sqlite3.connect(data/'control.sqlite');con.row_factory=sqlite3.Row
 run=con.execute('SELECT * FROM sis_backup_runs').fetchone()
 assert run['status']=='success',dict(run)
 assert (data/'backups'/run['filename']).exists()
 assert 'dummy-secret-password' not in (data/'control.sqlite').read_bytes().decode(errors='ignore')
 assert not list((data/'tmp').iterdir())
 print('OK: Laravel descriptografa a credencial em pipe; Python conclui o backup sem segredo no histórico.',flush=True)
 with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
 with tempfile.TemporaryFile() as log:
  server=subprocess.Popen([PHP,'-S',f'127.0.0.1:{port}','-t',str(ROOT/'public'),str(ROOT/'public/index.php')],cwd=ROOT,env=env,stdout=log,stderr=log)
  try:
   base=f'http://127.0.0.1:{port}'
   client=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
   for _ in range(50):
    try:page=client.open(base+'/').read().decode();break
    except OSError:time.sleep(.1)
   else:raise RuntimeError('Servidor Laravel não iniciou')
   assert '/build/assets/app-' in page
   token=re.search(r'name="csrf-token" content="([^"]+)"',page)[1]
   def call(path,body=None,csrf=None):
    req=urllib.request.Request(base+'/api'+path,data=json.dumps(body).encode() if body is not None else None,headers={'Accept':'application/json','Content-Type':'application/json',**({'X-CSRF-TOKEN':csrf} if csrf else {})})
    return client.open(req)
   try:call('/login',{'email':'qa@example.test','password':'test-password-123'})
   except urllib.error.HTTPError as e:assert e.code==419
   else:raise AssertionError('Login sem CSRF aceito')
   result=json.load(call('/login',{'email':'qa@example.test','password':'test-password-123'},token));token=result['csrf']
   overview=json.load(call('/overview'));assert len(overview['runs'])==1
   assert 'db_password' not in overview['databases'][0]
   bad={'database_server_id':1,'weekdays':[2,5],'start_time':'17:00','enabled':True}
   try:call('/schedules',bad,token)
   except urllib.error.HTTPError as e:assert e.code==422
   else:raise AssertionError('Agendamento às 17:00 aceito')
   bad['start_time']='17:30';json.load(call('/schedules',bad,token))
   encrypted=client.open(base+'/api/runs/1/download').read();assert encrypted.startswith(b'BKMGR001')
   json.load(call('/logout',{},token))
   print('OK: API Laravel real com sessão, CSRF, horários, segredo ocultado e download autenticado.',flush=True)
  finally:server.terminate();server.wait(timeout=10)
 con.close()
