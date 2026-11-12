import base64, fcntl, os, re, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'python'))
from pgcontrol import connect_raw, SCHEMA
os.umask(0o077)
data=Path(os.environ.get('BACKUP_DATA_PATH','/data'))
if not re.fullmatch(r'[a-z_][a-z0-9_]*',SCHEMA):raise RuntimeError('DB_SCHEMA inválido: '+SCHEMA)
with open(data/'init.lock','a') as lock:
    fcntl.flock(lock,fcntl.LOCK_EX)
    for d in ('keys','backups','tmp'):(data/d).mkdir(mode=0o700,exist_ok=True)
    with connect_raw() as con:
        # Schema próprio: isola as tabelas deste sistema das demais aplicações do mesmo banco.
        con.execute(f'CREATE SCHEMA IF NOT EXISTS "{SCHEMA}"')
        populated=con.execute('SELECT to_regclass(%s) IS NOT NULL',(f'"{SCHEMA}".users',)).fetchone()[0]
        if populated:populated=con.execute(f'SELECT EXISTS(SELECT 1 FROM "{SCHEMA}".users)').fetchone()[0]
    for path,content in [(data/'app.key',('base64:'+base64.b64encode(os.urandom(32)).decode()+'\n').encode()),(data/'keys/backup.key',os.urandom(32))]:
        if not path.exists():
            if populated:raise RuntimeError('Chave ausente em instalação existente. Restaure a chave original: '+str(path))
            with open(path,'xb') as f:f.write(content)
            path.chmod(0o600)
