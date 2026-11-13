#!/usr/bin/env python3
import os, sys
# A senha deve chegar só pelo ambiente, nunca pelo argv.
if any('dummy-secret-password' in a for a in sys.argv):
    sys.stderr.write('senha no argv');sys.exit(9)
if os.environ.get('PGPASSWORD')!='dummy-secret-password' or os.environ.get('PGSSLMODE')!='require':
    sys.stderr.write('ambiente PG incorreto');sys.exit(8)
if os.environ.get('BK_TEST_MODE')=='dumpfail':
    sys.stderr.write('FATAL: password authentication failed dummy-secret-password');sys.exit(1)
sys.stdout.write('-- PostgreSQL database dump\nCREATE TABLE example (id integer);\n')
for n in range(12000):
    sys.stdout.write('INSERT INTO example VALUES (' + str(n) + ');\n')
