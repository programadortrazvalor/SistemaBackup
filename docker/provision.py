import base64, fcntl, os
from pathlib import Path
os.umask(0o077)
data=Path(os.environ.get('BACKUP_DATA_PATH','/data'))
with open(data/'init.lock','a') as lock:
    fcntl.flock(lock,fcntl.LOCK_EX)
    for d in ('keys','backups','tmp'):(data/d).mkdir(mode=0o700,exist_ok=True)
    populated=(data/'control.sqlite').exists() and (data/'control.sqlite').stat().st_size>0
    for path,content in [(data/'app.key',('base64:'+base64.b64encode(os.urandom(32)).decode()+'\n').encode()),(data/'keys/backup.key',os.urandom(32))]:
        if not path.exists():
            if populated:raise RuntimeError('Chave ausente em instalação existente. Restaure a chave original: '+str(path))
            with open(path,'xb') as f:f.write(content)
            path.chmod(0o600)
    (data/'control.sqlite').touch(exist_ok=True)
