"""Conexão com o banco de controle (PostgreSQL), com interface compatível com o uso anterior de sqlite3."""
import os
import psycopg
from psycopg.rows import dict_row

SCHEMA=os.environ.get('DB_SCHEMA','trazvalor_backup')

def connect_raw():
    return psycopg.connect(host=os.environ['DB_HOST'],port=os.environ.get('DB_PORT','5432'),dbname=os.environ['DB_DATABASE'],
        user=os.environ['DB_USERNAME'],password=os.environ.get('DB_PASSWORD',''),sslmode=os.environ.get('DB_SSLMODE','prefer'),
        connect_timeout=30,autocommit=True,application_name='trazvalor-backup',options=f'-c search_path="{SCHEMA}"')

class Control:
    """con.execute(sql, params) com placeholders '?'; 'with con:' abre transação (commit/rollback), como no sqlite3."""
    def __init__(self):
        self.raw=connect_raw();self.raw.row_factory=dict_row;self._tx=None
    def execute(self,sql,params=()):
        return self.raw.execute(sql.replace('?','%s'),params)
    def __enter__(self):
        self._tx=self.raw.transaction();self._tx.__enter__();return self
    def __exit__(self,*exc):
        tx,self._tx=self._tx,None
        return tx.__exit__(*exc)
    def close(self):
        self.raw.close()
