import datetime as dt, gzip, os, sqlite3, sys, tempfile, unittest
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
