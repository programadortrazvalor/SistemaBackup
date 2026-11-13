#!/usr/bin/env python3
"""Worker local: agenda, consome fila e executa mysqldump/pg_dump/sqlite3 sem shell/senha no argv. Controle em PostgreSQL."""
import argparse, contextlib, datetime as dt, fcntl, gzip, hashlib, json, os
from pathlib import Path
import re, selectors, shutil, signal, subprocess, sys, tempfile, time
from zoneinfo import ZoneInfo
from crypto_stream import EncryptedWriter, verify, decrypt_to, export_zip
from pgcontrol import Control
UTC=dt.timezone.utc
ZONE=ZoneInfo('America/Cuiaba')
DATA=Path(os.environ.get('BACKUP_DATA_PATH','/data'))
APP=Path(os.environ.get('BACKUP_APP_PATH','/var/www/html'))
MYSQL=os.environ.get('MYSQL_BIN','/usr/bin/mysql')
DUMP=os.environ.get('MYSQLDUMP_BIN','/usr/bin/mysqldump')
PGDUMP=os.environ.get('PGDUMP_BIN','/usr/bin/pg_dump')
SQLITE=os.environ.get('SQLITE3_BIN','/usr/bin/sqlite3')
SQLITE_DIR=Path(os.environ.get('BACKUP_SQLITE_PATH','/sqlite'))
PG_SSL={'REQUIRED':'require','VERIFY_IDENTITY':'verify-full','DISABLED':'disable'}
PHP=os.environ.get('PHP_BIN','/usr/bin/php')
STOP=False

def now_utc(): return dt.datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S')
def connect():
    return Control()

def due(schedule, now):
    at=schedule['start_time']
    if not schedule['enabled'] or not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d',at) or at<='17:00': return None
    days=json.loads(schedule['weekdays']) if isinstance(schedule['weekdays'],str) else schedule['weekdays']
    if now.isoweekday() not in days: return None
    hour,minute=map(int,at.split(':'));planned=now.replace(hour=hour,minute=minute,second=0,microsecond=0)
    if 0 <= (now-planned).total_seconds() <= 21600: return planned.isoformat(timespec='minutes')
    return None

def enqueue_due(con, now):
    rows=con.execute('SELECT s.* FROM sis_backup_schedules s JOIN sis_database_servers d ON d.id=s.database_server_id WHERE d.enabled AND s.enabled').fetchall()
    with con:
        for s in rows:
            slot=due(s,now)
            if slot:
                stamp=now_utc()
                con.execute("INSERT INTO sis_backup_runs(database_server_id,backup_schedule_id,scheduled_for,source,status,created_at,updated_at) VALUES(?,?,?,'schedule','queued',?,?) ON CONFLICT DO NOTHING",(s['database_server_id'],s['id'],slot,stamp,stamp))

def settings(con):
    raw={r['key']:r['value'] for r in con.execute('SELECT key,value FROM sis_backup_settings').fetchall()}
    return {'retention_count':max(1,int(raw.get('retention_count',4))),'timeout':max(60,int(raw.get('timeout_minutes',360))*60),'minimum_free':max(0,int(raw.get('minimum_free_gb',1))*1024**3),'external':raw.get('external_copy','0')=='1'}

def beat(con):
    with con: con.execute("INSERT INTO sis_backup_settings(key,value) VALUES('worker_heartbeat',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(now_utc(),))

def redact(message, password):
    text=str(message)
    if password: text=text.replace(password,'[oculto]')
    return text[-4000:]

def client_options(payload):
    quote=lambda s:'"'+str(s).replace('\\','\\\\').replace('"','\\"').replace('\n','\\n').replace('\r','\\r')+'"'
    opts='[client]\nhost='+quote(payload['host'])+'\nport='+str(int(payload['port']))+'\nuser='+quote(payload['username'])+'\npassword='+quote(payload['password'])+'\nprotocol=TCP\nssl-mode='+payload['tls_mode']+'\n'
    ca=ca_path(payload)
    if ca: opts+='ssl-ca='+quote(ca)+'\n'
    opts+='[mysql]\nconnect-timeout=30\n'  # só o cliente mysql aceita; o mysqldump recusa essa opção no [client]
    return opts

def ca_path(payload):
    name=payload.get('ca_file')
    if not name: return None
    if not re.fullmatch(r'[a-zA-Z0-9_.-]+',name) or name in ('.','..'): raise ValueError('Certificado inválido.')
    ca=Path('/certs')/name
    if not ca.is_file(): raise ValueError('Certificado CA não encontrado em /certs.')
    return ca

def sqlite_file(payload):
    name=str(payload.get('database') or '')
    if not re.fullmatch(r'[a-zA-Z0-9_.-]+',name) or name in ('.','..'): raise ValueError('Nome de arquivo SQLite inválido.')
    path=(SQLITE_DIR/name).resolve()
    if path.parent!=SQLITE_DIR.resolve() or not path.is_file(): raise ValueError(f'Arquivo SQLite não encontrado em {SQLITE_DIR}.')
    return path

REMOTE_PATH=re.compile(r'[a-zA-Z0-9_./~-]+')
def remote_path(value):
    path=str(value or '')
    if not REMOTE_PATH.fullmatch(path) or len(path)>255 or '..' in path.split('/') or path.endswith('/'):raise ValueError('Caminho remoto do SQLite inválido.')
    return path

def sftp_download(payload, folder, opts, heartbeat):
    """Baixa o .sqlite (e o -wal, se existir) por SFTP. Chave do host fixada no 1º acesso (TOFU)."""
    import paramiko
    source=remote_path(payload['database']);target=folder/'database.sqlite'
    known=DATA/'keys/ssh_known_hosts';known.touch(mode=0o600,exist_ok=True)
    client=paramiko.SSHClient();client.load_host_keys(str(known))
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())  # 1ª conexão grava a chave; troca posterior é recusada
    start=time.monotonic();state={'beat':0}
    def progress(done,total):
        if STOP:raise RuntimeError('Worker interrompido; download descartado.')
        if time.monotonic()-start>opts['timeout']:raise RuntimeError('Download SFTP excedeu o tempo limite configurado.')
        if time.monotonic()-state['beat']>30:
            heartbeat();state['beat']=time.monotonic()
            if shutil.disk_usage(DATA).free<opts['minimum_free']:raise RuntimeError('Reserva mínima de espaço em disco atingida.')
    try:
        try:
            client.connect(payload['host'],port=int(payload.get('port') or 22),username=payload.get('username') or None,password=payload.get('password') or None,timeout=30,banner_timeout=30,auth_timeout=30,allow_agent=False,look_for_keys=False)
        except paramiko.BadHostKeyException:raise RuntimeError('A chave SSH do servidor mudou. Se a troca for legítima, remova o host de /data/keys/ssh_known_hosts.') from None
        except paramiko.AuthenticationException:raise RuntimeError('Usuário ou senha SSH recusados.') from None
        client.save_host_keys(str(known));os.chmod(known,0o600)
        sftp=client.open_sftp()
        try:
            try:size=sftp.stat(source).st_size
            except IOError:raise RuntimeError('Arquivo SQLite não encontrado no servidor: '+source) from None
            if shutil.disk_usage(DATA).free-(size or 0)<opts['minimum_free']:raise RuntimeError('Espaço insuficiente para baixar o arquivo SQLite.')
            sftp.get(source,str(target),callback=progress)
            with contextlib.suppress(IOError):sftp.stat(source+'-wal');sftp.get(source+'-wal',str(target)+'-wal',callback=progress)
        finally:sftp.close()
    finally:client.close()
    with open(target,'rb') as f:
        if f.read(16)!=b'SQLite format 3\x00':raise RuntimeError('O arquivo baixado não é um banco SQLite válido.')
    return target

def pg_env(payload):
    env={k:v for k,v in os.environ.items() if not k.startswith('PG')}
    env.update({'PGPASSWORD':str(payload.get('password') or ''),'PGSSLMODE':PG_SSL.get(payload.get('tls_mode'),'require'),'PGCONNECT_TIMEOUT':'30','PGAPPNAME':'backup-manager'})
    ca=ca_path(payload)
    if ca: env['PGSSLROOTCERT']=str(ca)
    return env

def command(argv, timeout, password=''):
    try:
        result=subprocess.run(argv,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=timeout,check=False)
    except subprocess.TimeoutExpired: raise RuntimeError('Tempo limite excedido no cliente MySQL.') from None
    if result.returncode: raise RuntimeError(redact(result.stderr.decode(errors='replace'),password) or 'Cliente MySQL retornou erro.')
    if len(result.stdout)>2*1024*1024: raise RuntimeError('Resposta do cliente excedeu limite de metadados.')
    return result.stdout.decode(errors='replace')

def dump_stream(argv, target, key, opts, password, heartbeat, env=None, label='mysqldump'):
    writer=EncryptedWriter(target,key);compressed=None;process=None;count=0;lastbeat=lastdisk=0;errors=bytearray()
    try:
        compressed=gzip.GzipFile(filename='',mode='wb',compresslevel=3,fileobj=writer,mtime=0)
        process=subprocess.Popen(argv,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True,env=env)
        selector=selectors.DefaultSelector()
        for stream,kind in ((process.stdout,'out'),(process.stderr,'err')):
            os.set_blocking(stream.fileno(),False);selector.register(stream,selectors.EVENT_READ,kind)
        start=time.monotonic()
        try:
            while selector.get_map():
                if STOP: raise RuntimeError('Worker interrompido; backup parcial descartado.')
                if time.monotonic()-start>opts['timeout']: raise RuntimeError('Backup excedeu o tempo limite configurado.')
                for event,_ in selector.select(timeout=.5):
                    block=os.read(event.fileobj.fileno(),65536)
                    if not block: selector.unregister(event.fileobj);continue
                    if event.data=='out':compressed.write(block);count+=len(block)
                    else: errors.extend(block);errors[:]=errors[-8192:]
                if time.monotonic()-lastbeat>30:heartbeat();lastbeat=time.monotonic()
                if time.monotonic()-lastdisk>3:
                    if shutil.disk_usage(DATA).free<opts['minimum_free']:raise RuntimeError('Reserva mínima de espaço em disco atingida.')
                    lastdisk=time.monotonic()
            remaining=max(.1,opts['timeout']-(time.monotonic()-start))
            code=process.wait(timeout=remaining)
        finally: selector.close()
        if code: raise RuntimeError(redact(errors.decode(errors='replace'),password) or f'{label} falhou.')
        if count<10: raise RuntimeError('Dump vazio ou inválido.')
        compressed.close();compressed=None;writer.finish()
        if verify(target,key,heartbeat)!=count:raise RuntimeError('Divergência na validação do tamanho SQL.')
        return count
    finally:
        if process:
            if process.poll() is None:
                os.killpg(process.pid,signal.SIGTERM)
                try:process.wait(timeout=3)
                except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait()
            process.stdout.close();process.stderr.close()
        if compressed:
            with contextlib.suppress(Exception):compressed.close()
        writer.abort()

def sha256(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()

def copy_external(source, digest):
    dest=Path(os.environ.get('BACKUP_EXTERNAL_PATH','/external'))
    if not dest.is_dir() or not os.access(dest,os.W_OK):raise RuntimeError('Backup local gerado; volume externo indisponível. Retenção não executada.')
    partial=dest/(source.name+'.partial')
    try:
        shutil.copyfile(source,partial);os.chmod(partial,0o600)
        if sha256(partial)!=digest:raise RuntimeError('Checksum da cópia externa divergiu.')
        os.replace(partial,dest/source.name)
    finally:partial.unlink(missing_ok=True)

def perform(payload, run_id, opts, heartbeat):
    key=(DATA/'keys/backup.key').read_bytes()
    driver=payload.get('driver') or 'mysql'
    name=f"db-{payload['id']}_{dt.datetime.now(ZONE):%Y-%m-%d_%H-%M-%S}_job-{run_id}.sql.gz.enc"
    tmp=DATA/'tmp'/(name+'.partial');final=DATA/'backups'/name;password=payload.get('password') or ''
    cnf=None;copydir=None
    try:
        if shutil.disk_usage(DATA).free<opts['minimum_free']:raise RuntimeError('Espaço em disco abaixo da reserva mínima.')
        if driver=='mysql':
            with tempfile.NamedTemporaryFile(mode='w',prefix='mysql-',suffix='.cnf',dir=DATA/'tmp',delete=False) as file:
                cnf=Path(file.name);os.chmod(cnf,0o600);file.write(client_options(payload))
            args,env,label,info=mysql_args(payload,cnf,password)
        elif driver=='pgsql':
            env=pg_env(payload);label='pg_dump';info={'driver':'pgsql'}
            args=[PGDUMP,'--no-password','--format=plain','--encoding=UTF8','--host='+payload['host'],'--port='+str(int(payload['port'])),'--username='+payload['username'],'--dbname='+payload['database']]
        elif driver=='sqlite':
            env=None;label='sqlite3'
            if payload.get('host'):
                copydir=Path(tempfile.mkdtemp(prefix='sqlite-',suffix='.partial',dir=DATA/'tmp'))
                path=sftp_download(payload,copydir,opts,heartbeat)
                info={'driver':'sqlite','origem':'sftp','host':payload['host'],'file':payload['database']}
                args=[SQLITE,'-bail',str(path),'.dump']  # cópia local: pode aplicar o WAL baixado
            else:
                path=sqlite_file(payload);info={'driver':'sqlite','origem':'local','file':path.name}
                args=[SQLITE,'-readonly','-bail',str(path),'.dump']
        else:raise RuntimeError('Tipo de banco não suportado: '+str(driver))
        count=dump_stream(args,tmp,key,opts,password,heartbeat,env,label)
        os.replace(tmp,final);digest=sha256(final)
        result={'filename':name,'size_bytes':final.stat().st_size,'sql_bytes':count,'sha256':digest,'details':json.dumps({**info,'external':opts['external'],'validation':'gzip + AES-GCM; restauração SQL ainda não testada'},ensure_ascii=False)}
        if opts['external']:copy_external(final,digest)
        return result
    except Exception as e:raise RuntimeError(redact(e,password)) from None
    finally:
        tmp.unlink(missing_ok=True)
        if cnf:cnf.unlink(missing_ok=True)
        if copydir:shutil.rmtree(copydir,ignore_errors=True)

def mysql_args(payload, cnf, password):
    base=['--defaults-extra-file='+str(cnf)]
    sql="SELECT COALESCE(ENGINE,'VIEW'),COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA=CONVERT(0x"+payload['database'].encode().hex()+" USING utf8mb4) GROUP BY ENGINE"
    engines=command([MYSQL,*base,'--batch','--skip-column-names','--execute='+sql],60,password).strip()
    if not engines:raise RuntimeError('Banco vazio, inexistente ou sem acesso aos metadados.')
    legacy=[line.split('\t')[0] for line in engines.splitlines() if line.split('\t')[0].upper() not in ('INNODB','VIEW')]
    if legacy and payload['consistency'] not in ('tables','locked'):raise RuntimeError('Motores não transacionais: '+', '.join(legacy)+'. Em "Consistência do backup", escolha "Bloqueio das tabelas do banco (MyISAM)".')
    helptext=command([DUMP,'--no-defaults','--help'],30)
    if 'set-gtid-purged' not in helptext:raise RuntimeError('Instale o cliente Oracle MySQL; o cliente MariaDB não é suportado por este worker.')
    args=[DUMP,*base,'--default-character-set=utf8mb4','--quick','--hex-blob','--routines','--events','--triggers','--no-tablespaces','--set-gtid-purged=OFF','--max-allowed-packet=256M']
    if 'column-statistics' in helptext:args.append('--column-statistics=0')
    args+={'locked':['--lock-all-tables'],'tables':['--lock-tables']}.get(payload['consistency'],['--single-transaction','--skip-lock-tables'])
    args+=['--',payload['database']]
    return args,None,'mysqldump',{'driver':'mysql','engines':engines}

def retention(con, database_id, keep, external):
    rows=con.execute("SELECT id,filename FROM sis_backup_runs WHERE database_server_id=? AND status='success' ORDER BY id DESC OFFSET ?",(database_id,keep)).fetchall()
    for row in rows:
        name=Path(row['filename']).name
        (DATA/'backups'/name).unlink(missing_ok=True)
        if external:(Path(os.environ.get('BACKUP_EXTERNAL_PATH','/external'))/name).unlink(missing_ok=True)
        with con:con.execute("UPDATE sis_backup_runs SET status='expired',updated_at=? WHERE id=?",(now_utc(),row['id']))

def get_payload(run_id):
    result=subprocess.run([PHP,str(APP/'artisan'),'backups:payload',str(run_id),'--no-ansi'],cwd=APP,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=60,check=False)
    if result.returncode:raise RuntimeError('Laravel não conseguiu abrir a credencial. Confira APP_KEY, banco de controle e permissões.')
    return json.loads(result.stdout)

def notify(run_id):
    try:
        p=subprocess.run([PHP,str(APP/'artisan'),'backups:notify',str(run_id),'--no-ansi'],cwd=APP,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=60,check=False)
        if p.returncode:print('Falha ao enviar alerta. Confira MAIL_*.',flush=True)
    except Exception:print('Falha ao enviar alerta. Confira MAIL_*.',flush=True)

def tick(con, schedule=True):
    beat(con)
    if schedule:enqueue_due(con,dt.datetime.now(ZONE))
    while not STOP:
        with con:
            run=con.execute("SELECT * FROM sis_backup_runs WHERE status='queued' ORDER BY id LIMIT 1 FOR UPDATE SKIP LOCKED").fetchone()
            if not run:return
            database=con.execute('SELECT enabled FROM sis_database_servers WHERE id=?',(run['database_server_id'],)).fetchone()
            schedule_enabled=True
            if run['backup_schedule_id']:
                row=con.execute('SELECT enabled FROM sis_backup_schedules WHERE id=?',(run['backup_schedule_id'],)).fetchone();schedule_enabled=bool(row and row['enabled'])
            expired_slot=False
            if run['source']=='schedule':
                try:
                    planned=dt.datetime.fromisoformat(run['scheduled_for']);localnow=dt.datetime.now(ZONE)
                    expired_slot=localnow.date()!=planned.date() or not 0<=(localnow-planned).total_seconds()<=21600 or localnow.strftime('%H:%M')<='17:00'
                except (ValueError,TypeError):expired_slot=True
            if not database or not database['enabled'] or not schedule_enabled or expired_slot:
                con.execute("UPDATE sis_backup_runs SET status='cancelled',finished_at=?,updated_at=?,error='Banco/agendamento pausado ou janela de execução encerrada.' WHERE id=?",(now_utc(),now_utc(),run['id']));continue
            con.execute("UPDATE sis_backup_runs SET status='running',started_at=?,updated_at=? WHERE id=?",(now_utc(),now_utc(),run['id']))
        try:
            payload=get_payload(run['id']);opts=settings(con)
            result=perform(payload,run['id'],opts,lambda:beat(con))
            with con:
                con.execute("UPDATE sis_backup_runs SET status='success',finished_at=?,updated_at=?,filename=?,size_bytes=?,sql_bytes=?,sha256=?,details=? WHERE id=?",(now_utc(),now_utc(),result['filename'],result['size_bytes'],result['sql_bytes'],result['sha256'],result['details'],run['id']))
            try:retention(con,run['database_server_id'],opts['retention_count'],opts['external'])
            except Exception:
                with con:con.execute('UPDATE sis_backup_runs SET error=? WHERE id=?',('Backup concluído; retenção falhou. Confira disco e permissões.',run['id']))
            print(f"Backup #{run['id']} concluído.",flush=True)
        except Exception as e:
            with con:con.execute("UPDATE sis_backup_runs SET status='failed',finished_at=?,updated_at=?,error=? WHERE id=?",(now_utc(),now_utc(),str(e)[-4000:],run['id']))
            print(f"Backup #{run['id']} falhou. Consulte o histórico.",flush=True);notify(run['id'])
        beat(con)

def stop(signum, frame):
    global STOP
    STOP=True

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--once',action='store_true',help='Processa fila e sai (alternativa ao daemon/cron).')
    sub=parser.add_subparsers(dest='command')
    decrypt=sub.add_parser('decrypt');decrypt.add_argument('--input',required=True);decrypt.add_argument('--output',required=True)
    tozip=sub.add_parser('zip');tozip.add_argument('--input',required=True);tozip.add_argument('--output',required=True);tozip.add_argument('--name',required=True)
    args=parser.parse_args();os.umask(0o077)
    if args.command=='zip':
        if not re.fullmatch(r'[a-zA-Z0-9_.-]+\.sql',args.name):raise ValueError('Nome interno inválido.')
        export_zip(args.input,args.output,(DATA/'keys/backup.key').read_bytes(),args.name);return
    if args.command=='decrypt':
        decrypt_to(args.input,args.output,(DATA/'keys/backup.key').read_bytes());print('Arquivo autenticado e descriptografado. Valide o gzip e restaure em banco separado.');return
    for folder in ('tmp','backups','keys'):(DATA/folder).mkdir(parents=True,exist_ok=True,mode=0o700)
    with open(DATA/'worker.lock','a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:print('Outro worker está ativo.',flush=True);return
        signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
        con=connect()
        try:
            for pattern in ('mysql-*.cnf','*.partial','download-*.zip'):
                for stale in (DATA/'tmp').glob(pattern):
                    if stale.is_dir():shutil.rmtree(stale,ignore_errors=True)
                    else:stale.unlink(missing_ok=True)
            with con:con.execute("UPDATE sis_backup_runs SET status='failed',finished_at=?,updated_at=?,error='Worker interrompido. Confira os recursos e solicite um novo teste.' WHERE status='running'",(now_utc(),now_utc()))
            while not STOP:
                tick(con)
                if args.once:break
                for _ in range(15):
                    if STOP:break
                    time.sleep(1)
        finally:con.close()

if __name__=='__main__':
    try:main()
    except Exception as e:print('Erro do worker: '+str(e),file=sys.stderr);sys.exit(1)
