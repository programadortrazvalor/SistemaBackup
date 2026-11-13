import datetime as dt, gzip, os, shutil, sqlite3, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import worker
from crypto_stream import EncryptedWriter, plaintext_chunks, verify, decrypt_to

class WorkerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)
        for d in ('keys','tmp','backups'):(self.path/d).mkdir()
        self.key=os.urandom(32);(self.path/'keys/backup.key').write_bytes(self.key)
        self.patch=patch.object(worker,'DATA',self.path);self.patch.start()
    def tearDown(self):self.patch.stop();self.temp.cleanup()
    def archive(self):
        original=os.urandom(2400000);out=self.path/'test.enc';w=EncryptedWriter(out,self.key)
        with gzip.GzipFile(fileobj=w,mode='wb') as gz:gz.write(original)
        w.finish();return original,out
    def test_encryption_roundtrip_and_gzip_validation(self):
        original,out=self.archive();self.assertEqual(verify(out,self.key),len(original))
        self.assertEqual(gzip.decompress(b''.join(plaintext_chunks(out,self.key))),original)
    def test_tampering_and_truncation_are_rejected(self):
        _,out=self.archive();raw=bytearray(out.read_bytes());raw[45]^=1;out.write_bytes(raw)
        with self.assertRaises(Exception):list(plaintext_chunks(out,self.key))
        _,out2=self.archive_named()
        out2.write_bytes(out2.read_bytes()[:-10])
        with self.assertRaises(Exception):list(plaintext_chunks(out2,self.key))
    def archive_named(self):
        p=self.path/'other.enc';w=EncryptedWriter(p,self.key);w.write(gzip.compress(b'test'));w.finish();return b'test',p
    def test_wrong_key_and_failed_decrypt_remove_output(self):
        _,out=self.archive();target=self.path/'plain.gz'
        with self.assertRaises(Exception):decrypt_to(out,target,os.urandom(32))
        self.assertFalse(target.exists())
    def test_schedule_days_time_and_timezone(self):
        s={'enabled':1,'weekdays':'[2,5]','start_time':'17:30'}
        def at(t):return dt.datetime.fromisoformat(t).replace(tzinfo=worker.ZONE)
        self.assertIsNone(worker.due(s,at('2026-11-10T17:29')))
        self.assertIsNotNone(worker.due(s,at('2026-11-10T17:30')))
        self.assertIsNotNone(worker.due(s,at('2026-11-13T18:00')))
        self.assertIsNone(worker.due(s,at('2026-11-11T17:30')))
        self.assertIsNone(worker.due(s,at('2026-11-10T23:31')))
        s['start_time']='17:00';self.assertIsNone(worker.due(s,at('2026-11-10T17:30')))
    def test_secret_options_escape_password(self):
        p={'host':'localhost','port':3306,'username':'test','password':'a"b\\c\nd','tls_mode':'REQUIRED'}
        text=worker.client_options(p);self.assertIn('password="a\\"b\\\\c\\nd"',text)
        # mysqldump lê [client] e recusa connect-timeout; a opção só pode ficar em [mysql].
        self.assertNotIn('connect-timeout',text.split('[mysql]')[0]);self.assertIn('[mysql]\nconnect-timeout=30',text)
    def test_process_dump_success_failure_and_cleanup(self):
        here=Path(__file__).parent
        payload={'id':1,'name':'QA','host':'localhost','port':3306,'database':'qa','username':'test','password':'dummy-secret-password','tls_mode':'REQUIRED','consistency':'transaction'}
        opts={'minimum_free':0,'timeout':30,'external':False}
        with patch.object(worker,'MYSQL',str(here/'fake-mysql.py')),patch.object(worker,'DUMP',str(here/'fake-mysqldump.py')):
            with patch.dict(os.environ,{'BK_TEST_MODE':'ok'}):result=worker.perform(payload,1,opts,lambda:None)
            self.assertTrue((self.path/'backups'/result['filename']).exists());self.assertGreater(result['sql_bytes'],100)
            with patch.dict(os.environ,{'BK_TEST_MODE':'dumpfail'}):
                with self.assertRaisesRegex(RuntimeError,'oculto'):worker.perform(payload,2,opts,lambda:None)
            with patch.dict(os.environ,{'BK_TEST_MODE':'myisam'}):
                with self.assertRaisesRegex(RuntimeError,'não transacionais'):worker.perform(payload,3,opts,lambda:None)
                worker.perform({**payload,'consistency':'tables'},4,opts,lambda:None)
            self.assertEqual(list((self.path/'tmp').iterdir()),[])
    def test_postgres_dump_uses_env_password(self):
        here=Path(__file__).parent
        payload={'id':2,'driver':'pgsql','name':'PG','host':'localhost','port':5432,'database':'qa','username':'test','password':'dummy-secret-password','tls_mode':'REQUIRED','consistency':'transaction'}
        opts={'minimum_free':0,'timeout':30,'external':False}
        with patch.object(worker,'PGDUMP',str(here/'fake-pg_dump.py')):
            with patch.dict(os.environ,{'BK_TEST_MODE':'ok'}):result=worker.perform(payload,10,opts,lambda:None)
            self.assertTrue((self.path/'backups'/result['filename']).exists());self.assertIn('pgsql',result['details'])
            with patch.dict(os.environ,{'BK_TEST_MODE':'dumpfail'}):
                with self.assertRaisesRegex(RuntimeError,'oculto'):worker.perform(payload,11,opts,lambda:None)
        self.assertEqual(list((self.path/'tmp').iterdir()),[])
    def test_sqlite_path_is_confined(self):
        folder=self.path/'sqlite';folder.mkdir()
        with patch.object(worker,'SQLITE_DIR',folder):
            for bad in ('../keys/backup.key','..','x/y.db','missing.db'):
                with self.assertRaises(ValueError):worker.sqlite_file({'database':bad})
    @unittest.skipUnless(shutil.which('sqlite3'),'cliente sqlite3 ausente')
    def test_sqlite_dump(self):
        folder=self.path/'sqlite';folder.mkdir();db=folder/'qa.sqlite'
        con=sqlite3.connect(db);con.execute('CREATE TABLE t(id INTEGER)');con.executemany('INSERT INTO t VALUES(?)',[(n,) for n in range(500)]);con.commit();con.close()
        payload={'id':3,'driver':'sqlite','name':'Local','database':'qa.sqlite','password':None}
        with patch.object(worker,'SQLITE_DIR',folder),patch.object(worker,'SQLITE',shutil.which('sqlite3')):
            result=worker.perform(payload,20,{'minimum_free':0,'timeout':30,'external':False},lambda:None)
        self.assertGreater(result['sql_bytes'],1000)
    def test_export_zip_contains_plain_sql(self):
        import zipfile
        from crypto_stream import export_zip
        sql=b'CREATE TABLE t(id INT);\n'+b'INSERT INTO t VALUES (1);\n'*200000
        enc=self.path/'b.enc';w=EncryptedWriter(enc,self.key)
        with gzip.GzipFile(fileobj=w,mode='wb') as gz:gz.write(sql)
        w.finish();out=self.path/'b.zip'
        export_zip(enc,out,self.key,'dy_2026.sql')
        with zipfile.ZipFile(out) as zf:self.assertEqual(zf.namelist(),['dy_2026.sql']);self.assertEqual(zf.read('dy_2026.sql'),sql)
        with self.assertRaises(Exception):export_zip(enc,self.path/'bad.zip',os.urandom(32),'x.sql')
        self.assertFalse((self.path/'bad.zip').exists())
        # Modo streaming (--output=-): ZIP pela saída padrão num pipe; chave errada não emite nenhum byte.
        import subprocess, io
        script=Path(__file__).resolve().parents[1]/'worker.py';env={**os.environ,'BACKUP_DATA_PATH':str(self.path)}
        p=subprocess.run([sys.executable,str(script),'zip','--input='+str(enc),'--output=-','--name=dy.sql'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env)
        self.assertEqual(p.returncode,0,p.stderr)
        with zipfile.ZipFile(io.BytesIO(p.stdout)) as zf:self.assertEqual(zf.read('dy.sql'),sql)
        (self.path/'keys/backup.key').write_bytes(os.urandom(32))
        p=subprocess.run([sys.executable,str(script),'zip','--input='+str(enc),'--output=-','--name=dy.sql'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env)
        self.assertNotEqual(p.returncode,0);self.assertEqual(p.stdout,b'')
    def test_remote_path_validation(self):
        self.assertEqual(worker.remote_path('/home/u/app/db.sqlite'),'/home/u/app/db.sqlite')
        for bad in ('/home/../etc/shadow','..','a b','x;rm','/dir/'):
            with self.assertRaises(ValueError):worker.remote_path(bad)
    @unittest.skipUnless(shutil.which('sqlite3'),'cliente sqlite3 ausente')
    def test_sqlite_sftp_download_and_dump(self):
        import types
        source=self.path/'remote.sqlite';con=sqlite3.connect(source);con.execute('CREATE TABLE t(id INTEGER)');con.executemany('INSERT INTO t VALUES(?)',[(n,) for n in range(500)]);con.commit();con.close()
        seen={}
        class AuthErr(Exception):pass
        class SFTP:
            def stat(self,p):
                if p!='/srv/app.sqlite':raise IOError(p)
                return types.SimpleNamespace(st_size=source.stat().st_size)
            def get(self,p,local,callback=None):shutil.copyfile(source,local);callback and callback(1,1)
            def close(self):pass
        class Client:
            def load_host_keys(self,f):seen['known']=f
            def set_missing_host_key_policy(self,p):pass
            def connect(self,host,**kw):seen.update(host=host,**kw)
            def save_host_keys(self,f):Path(f).write_text('')
            def open_sftp(self):return SFTP()
            def close(self):pass
        fake=types.SimpleNamespace(SSHClient=Client,AutoAddPolicy=lambda:None,BadHostKeyException=type('B',(Exception,),{}),AuthenticationException=AuthErr)
        payload={'id':4,'driver':'sqlite','name':'R','host':'srv.example','port':22,'database':'/srv/app.sqlite','username':'u','password':'dummy-secret-password'}
        with patch.dict(sys.modules,{'paramiko':fake}),patch.object(worker,'SQLITE',shutil.which('sqlite3')):
            result=worker.perform(payload,30,{'minimum_free':0,'timeout':30,'external':False},lambda:None)
            self.assertGreater(result['sql_bytes'],1000);self.assertEqual(seen['host'],'srv.example');self.assertFalse(seen['look_for_keys'])
            with self.assertRaisesRegex(RuntimeError,'não encontrado'):worker.perform({**payload,'database':'/srv/outro.sqlite'},31,{'minimum_free':0,'timeout':30,'external':False},lambda:None)
        self.assertEqual(list((self.path/'tmp').iterdir()),[])
    def test_external_copy_failure_preserves_local(self):
        source=self.path/'backups/local.enc';source.write_bytes(b'ciphertext')
        with patch.dict(os.environ,{'BACKUP_EXTERNAL_PATH':str(self.path/'missing')}):
            with self.assertRaisesRegex(RuntimeError,'volume externo'):worker.copy_external(source,worker.sha256(source))
        self.assertTrue(source.exists())
    def test_external_copy_checksum(self):
        source=self.path/'backups/local.enc';source.write_bytes(b'ciphertext');remote=self.path/'remote';remote.mkdir()
        with patch.dict(os.environ,{'BACKUP_EXTERNAL_PATH':str(remote)}):worker.copy_external(source,worker.sha256(source))
        self.assertEqual(source.read_bytes(),(remote/source.name).read_bytes())

if __name__=='__main__':unittest.main()
