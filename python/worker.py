#!/usr/bin/env python3
"""Worker local: agenda, consome fila e executa mysqldump sem shell/senha no argv."""
import argparse, contextlib, datetime as dt, fcntl, gzip, hashlib, json, os
from pathlib import Path
import re, selectors, shutil, signal, sqlite3, subprocess, sys, tempfile, time
from zoneinfo import ZoneInfo
from crypto_stream import EncryptedWriter, verify, decrypt_to
UTC=dt.timezone.utc
ZONE=ZoneInfo('America/Cuiaba')
DATA=Path(os.environ.get('BACKUP_DATA_PATH','/data'))
APP=Path(os.environ.get('BACKUP_APP_PATH','/var/www/html'))
MYSQL=os.environ.get('MYSQL_BIN','/usr/bin/mysql')
DUMP=os.environ.get('MYSQLDUMP_BIN','/usr/bin/mysqldump')
PHP=os.environ.get('PHP_BIN','/usr/bin/php')
STOP=False

def now_utc(): return dt.datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S')
def connect():
    con=sqlite3.connect(DATA/'control.sqlite',timeout=10)
    con.row_factory=sqlite3.Row
    con.execute('PRAGMA foreign_keys=ON');con.execute('PRAGMA busy_timeout=10000');con.execute('PRAGMA journal_mode=WAL')
    return con

def due(schedule, now):
    at=schedule['start_time']
    if not schedule['enabled'] or not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d',at) or at<='17:00': return None
    days=json.loads(schedule['weekdays']) if isinstance(schedule['weekdays'],str) else schedule['weekdays']
    if now.isoweekday() not in days: return None
    hour,minute=map(int,at.split(':'));planned=now.replace(hour=hour,minute=minute,second=0,microsecond=0)
    if 0 <= (now-planned).total_seconds() <= 21600: return planned.isoformat(timespec='minutes')
    return None

def enqueue_due(con, now):
    rows=con.execute('SELECT s.* FROM backup_schedules s JOIN database_servers d ON d.id=s.database_server_id WHERE d.enabled=1 AND s.enabled=1').fetchall()
    with con:
        for s in rows:
            slot=due(s,now)
            if slot:
                stamp=now_utc()
                con.execute("INSERT OR IGNORE INTO backup_runs(database_server_id,backup_schedule_id,scheduled_for,source,status,created_at,updated_at) VALUES(?,?,?,'schedule','queued',?,?)",(s['database_server_id'],s['id'],slot,stamp,stamp))

def settings(con):
    raw=dict(con.execute('SELECT key,value FROM backup_settings').fetchall())
    return {'retention_count':max(1,int(raw.get('retention_count',4))),'timeout':max(60,int(raw.get('timeout_minutes',360))*60),'minimum_free':max(0,int(raw.get('minimum_free_gb',1))*1024**3),'external':raw.get('external_copy','0')=='1'}

def beat(con):
    with con: con.execute("INSERT INTO backup_settings(key,value) VALUES('worker_heartbeat',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(now_utc(),))

def redact(message, password):
    text=str(message)
    if password: text=text.replace(password,'[oculto]')
    return text[-4000:]

def client_options(payload):
    quote=lambda s:'"'+str(s).replace('\\','\\\\').replace('"','\\"').replace('\n','\\n').replace('\r','\\r')+'"'
    opts='[client]\nhost='+quote(payload['host'])+'\nport='+str(int(payload['port']))+'\nuser='+quote(payload['username'])+'\npassword='+quote(payload['password'])+'\nprotocol=TCP\nconnect-timeout=30\nssl-mode='+payload['tls_mode']+'\n'
    if payload.get('ca_file'):
        name=payload['ca_file']
        if not re.fullmatch(r'[a-zA-Z0-9_.-]+',name) or name in ('.','..'): raise ValueError('Certificado inválido.')
        ca=Path('/certs')/name
        if not ca.is_file(): raise ValueError('Certificado CA não encontrado em /certs.')
        opts+='ssl-ca='+quote(ca)+'\n'
    return opts

def command(argv, timeout, password=''):
    try:
        result=subprocess.run(argv,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=timeout,check=False)
    except subprocess.TimeoutExpired: raise RuntimeError('Tempo limite excedido no cliente MySQL.') from None
    if result.returncode: raise RuntimeError(redact(result.stderr.decode(errors='replace'),password) or 'Cliente MySQL retornou erro.')
    if len(result.stdout)>2*1024*1024: raise RuntimeError('Resposta do cliente excedeu limite de metadados.')
    return result.stdout.decode(errors='replace')

def dump_stream(argv, target, key, opts, password, heartbeat):
    writer=EncryptedWriter(target,key);compressed=None;process=None;count=0;lastbeat=lastdisk=0;errors=bytearray()
    try:
        compressed=gzip.GzipFile(filename='',mode='wb',compresslevel=3,fileobj=writer,mtime=0)
        process=subprocess.Popen(argv,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
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
        if code: raise RuntimeError(redact(errors.decode(errors='replace'),password) or 'mysqldump falhou.')
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
    name=f"db-{payload['id']}_{dt.datetime.now(ZONE):%Y-%m-%d_%H-%M-%S}_job-{run_id}.sql.gz.enc"
    tmp=DATA/'tmp'/(name+'.partial');final=DATA/'backups'/name;password=payload['password']
    cnf=None
    try:
        if shutil.disk_usage(DATA).free<opts['minimum_free']:raise RuntimeError('Espaço em disco abaixo da reserva mínima.')
        with tempfile.NamedTemporaryFile(mode='w',prefix='mysql-',suffix='.cnf',dir=DATA/'tmp',delete=False) as file:
            cnf=Path(file.name);os.chmod(cnf,0o600);file.write(client_options(payload))
        base=['--defaults-extra-file='+str(cnf)]
        sql="SELECT COALESCE(ENGINE,'VIEW'),COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA=CONVERT(0x"+payload['database'].encode().hex()+" USING utf8mb4) GROUP BY ENGINE"
        engines=command([MYSQL,*base,'--batch','--skip-column-names','--execute='+sql],60,password).strip()
        if not engines:raise RuntimeError('Banco vazio, inexistente ou sem acesso aos metadados.')
        legacy=[line.split('\t')[0] for line in engines.splitlines() if line.split('\t')[0].upper() not in ('INNODB','VIEW')]
        if legacy and payload['consistency']!='locked':raise RuntimeError('Motores não transacionais: '+', '.join(legacy)+'. Configure bloqueio global somente em janela de manutenção.')
        helptext=command([DUMP,'--no-defaults','--help'],30)
        if 'set-gtid-purged' not in helptext:raise RuntimeError('Instale o cliente Oracle MySQL; o cliente MariaDB não é suportado por este worker.')
        args=[DUMP,*base,'--default-character-set=utf8mb4','--quick','--hex-blob','--routines','--events','--triggers','--no-tablespaces','--set-gtid-purged=OFF','--max-allowed-packet=256M']
        if 'column-statistics' in helptext:args.append('--column-statistics=0')
        args+=['--lock-all-tables'] if payload['consistency']=='locked' else ['--single-transaction','--skip-lock-tables']
        args+=['--',payload['database']]
        count=dump_stream(args,tmp,key,opts,password,heartbeat)
        os.replace(tmp,final);digest=sha256(final)
        result={'filename':name,'size_bytes':final.stat().st_size,'sql_bytes':count,'sha256':digest,'details':json.dumps({'engines':engines,'external':opts['external'],'validation':'gzip + AES-GCM; restauração SQL ainda não testada'},ensure_ascii=False)}
        if opts['external']:copy_external(final,digest)
        return result
    except Exception as e:raise RuntimeError(redact(e,password)) from None
    finally:
        tmp.unlink(missing_ok=True)
        if cnf:cnf.unlink(missing_ok=True)

def retention(con, database_id, keep, external):
    rows=con.execute("SELECT id,filename FROM backup_runs WHERE database_server_id=? AND status='success' ORDER BY id DESC LIMIT -1 OFFSET ?",(database_id,keep)).fetchall()
    for row in rows:
        name=Path(row['filename']).name
        (DATA/'backups'/name).unlink(missing_ok=True)
        if external:(Path(os.environ.get('BACKUP_EXTERNAL_PATH','/external'))/name).unlink(missing_ok=True)
        with con:con.execute("UPDATE backup_runs SET status='expired',updated_at=? WHERE id=?",(now_utc(),row['id']))

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
            con.execute('BEGIN IMMEDIATE')
            run=con.execute("SELECT * FROM backup_runs WHERE status='queued' ORDER BY id LIMIT 1").fetchone()
            if not run:return
            database=con.execute('SELECT enabled FROM database_servers WHERE id=?',(run['database_server_id'],)).fetchone()
            schedule_enabled=True
            if run['backup_schedule_id']:
                row=con.execute('SELECT enabled FROM backup_schedules WHERE id=?',(run['backup_schedule_id'],)).fetchone();schedule_enabled=bool(row and row['enabled'])
            expired_slot=False
            if run['source']=='schedule':
                try:
                    planned=dt.datetime.fromisoformat(run['scheduled_for']);localnow=dt.datetime.now(ZONE)
                    expired_slot=localnow.date()!=planned.date() or not 0<=(localnow-planned).total_seconds()<=21600 or localnow.strftime('%H:%M')<='17:00'
                except (ValueError,TypeError):expired_slot=True
            if not database or not database['enabled'] or not schedule_enabled or expired_slot:
                con.execute("UPDATE backup_runs SET status='cancelled',finished_at=?,updated_at=?,error='Banco/agendamento pausado ou janela de execução encerrada.' WHERE id=?",(now_utc(),now_utc(),run['id']));continue
            con.execute("UPDATE backup_runs SET status='running',started_at=?,updated_at=? WHERE id=?",(now_utc(),now_utc(),run['id']))
        try:
            payload=get_payload(run['id']);opts=settings(con)
            result=perform(payload,run['id'],opts,lambda:beat(con))
            with con:
                con.execute("UPDATE backup_runs SET status='success',finished_at=?,updated_at=?,filename=?,size_bytes=?,sql_bytes=?,sha256=?,details=? WHERE id=?",(now_utc(),now_utc(),result['filename'],result['size_bytes'],result['sql_bytes'],result['sha256'],result['details'],run['id']))
            try:retention(con,run['database_server_id'],opts['retention_count'],opts['external'])
            except Exception:
                with con:con.execute('UPDATE backup_runs SET error=? WHERE id=?',('Backup concluído; retenção falhou. Confira disco e permissões.',run['id']))
            print(f"Backup #{run['id']} concluído.",flush=True)
        except Exception as e:
            with con:con.execute("UPDATE backup_runs SET status='failed',finished_at=?,updated_at=?,error=? WHERE id=?",(now_utc(),now_utc(),str(e)[-4000:],run['id']))
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
    args=parser.parse_args();os.umask(0o077)
    if args.command=='decrypt':
        decrypt_to(args.input,args.output,(DATA/'keys/backup.key').read_bytes());print('Arquivo autenticado e descriptografado. Valide o gzip e restaure em banco separado.');return
    for folder in ('tmp','backups','keys'):(DATA/folder).mkdir(parents=True,exist_ok=True,mode=0o700)
    with open(DATA/'worker.lock','a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:print('Outro worker está ativo.',flush=True);return
        signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
        con=connect()
        try:
            for pattern in ('mysql-*.cnf','*.partial'):
                for stale in (DATA/'tmp').glob(pattern):stale.unlink(missing_ok=True)
            with con:con.execute("UPDATE backup_runs SET status='failed',finished_at=?,updated_at=?,error='Worker interrompido. Confira os recursos e solicite um novo teste.' WHERE status='running'",(now_utc(),now_utc()))
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
