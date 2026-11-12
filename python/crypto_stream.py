"""Formato versionado com AES-256-GCM por bloco e chave de arquivo via HKDF.
Cada arquivo exige marcador final autenticado. Memória limitada a blocos de 1 MiB.
"""
import os, struct, zlib, time
from pathlib import Path
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes
MAGIC = b'BKMGR001'
CHUNK = 1024 * 1024

def key_for(master, salt):
    if len(master) != 32: raise ValueError('Chave de backup inválida: esperado 32 bytes.')
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=salt, info=b'BackupManager/file/v1').derive(master)

def exact(stream, length):
    data = bytearray()
    while len(data) < length:
        block = stream.read(length - len(data))
        if not block: raise ValueError('Backup truncado.')
        data.extend(block)
    return bytes(data)

class EncryptedWriter:
    def __init__(self, path, master):
        self.out = open(path, 'xb'); os.chmod(path, 0o600)
        self.header = MAGIC + os.urandom(16)
        self.aead = AESGCM(key_for(master, self.header[8:]))
        self.out.write(self.header)
        self.counter = 0; self.buffer = bytearray(); self.closed = False
    def _frame(self, data, final=False):
        if self.counter >= 2**32: raise ValueError('Limite de blocos excedido.')
        count = struct.pack('>I', self.counter); kind = bytes([int(final)])
        cipher = self.aead.encrypt(b'\0'*8+count, data, self.header+kind+count)
        self.out.write(kind + struct.pack('>I',len(cipher)) + cipher)
        self.counter += 1
    def write(self, data):
        if self.closed: raise ValueError('Arquivo já finalizado.')
        self.buffer.extend(data)
        while len(self.buffer) >= CHUNK:
            self._frame(bytes(self.buffer[:CHUNK])); del self.buffer[:CHUNK]
        return len(data)
    def flush(self): self.out.flush()
    def finish(self):
        if self.closed: return
        if self.buffer: self._frame(bytes(self.buffer)); self.buffer.clear()
        self._frame(b'', True); self.out.flush(); os.fsync(self.out.fileno()); self.out.close(); self.closed=True
    def abort(self):
        if not self.closed: self.out.close(); self.closed=True

def plaintext_chunks(path, master):
    with open(path,'rb') as stream:
        header = exact(stream,24)
        if header[:8] != MAGIC: raise ValueError('Formato de backup inválido.')
        aead = AESGCM(key_for(master,header[8:])); counter=0
        while True:
            kind=exact(stream,1); size=struct.unpack('>I',exact(stream,4))[0]
            if kind not in (b'\0',b'\1') or not 16<=size<=CHUNK+16 or counter>=2**32: raise ValueError('Bloco inválido.')
            count=struct.pack('>I',counter)
            plain=aead.decrypt(b'\0'*8+count,exact(stream,size),header+kind+count); counter+=1
            if kind==b'\1':
                if plain or stream.read(1): raise ValueError('Final do backup inválido.')
                return
            yield plain

def verify(path, master, progress=None):
    last_beat=0
    dec=zlib.decompressobj(16+zlib.MAX_WBITS); total=0
    for chunk in plaintext_chunks(path,master):
        if progress and time.monotonic()-last_beat>30:
            progress(); last_beat=time.monotonic()
        while chunk:
            out=dec.decompress(chunk,CHUNK); total+=len(out); chunk=dec.unconsumed_tail
        if dec.unused_data: raise ValueError('Dados extras após gzip.')
    if not dec.eof: raise ValueError('Gzip incompleto.')
    return total

def decrypt_to(path, target, master):
    created=False
    try:
        with open(target,'xb') as out:
            created=True; os.chmod(target,0o600)
            for chunk in plaintext_chunks(path,master): out.write(chunk)
            out.flush(); os.fsync(out.fileno())
    except BaseException:
        if created: Path(target).unlink(missing_ok=True)
        raise
