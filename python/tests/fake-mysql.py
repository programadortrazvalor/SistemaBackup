#!/usr/bin/env python3
import os, sys
mode = os.environ.get('BK_TEST_MODE', 'ok')
if mode == 'connection':
    sys.stderr.write('Access denied: dummy-secret-password')
    sys.exit(2)
print('MyISAM\t1' if mode == 'myisam' else 'InnoDB\t2')
