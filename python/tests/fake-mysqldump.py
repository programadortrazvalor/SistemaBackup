#!/usr/bin/env python3
import os, sys
if '--help' in sys.argv:
    print('set-gtid-purged column-statistics')
    sys.exit(0)
mode = os.environ.get('BK_TEST_MODE', 'ok')
if mode == 'dumpfail':
    sys.stdout.write('-- partial dump\n')
    sys.stderr.write('Lost connection dummy-secret-password')
    sys.exit(3)
sys.stdout.write('-- MySQL dump\nCREATE TABLE example (id INT);\n')
for n in range(12000):
    sys.stdout.write("INSERT INTO example VALUES (" + str(n) + ");\n")
sys.stdout.write('-- Dump completed\n')
