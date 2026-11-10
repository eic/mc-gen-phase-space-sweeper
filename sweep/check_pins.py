"""Check that every file the sweep will read still matches its pin (run after resolve.py).

Usage: python3 sweep/check_pins.py <campaign>

Stats each run/<campaign>/manifest.json file on EIC-XRD and compares the size, and for
files pinned from an xrootd listing (no Rucio checksum) also the mtime.
Exits non-zero on any mismatch, so a replaced or regenerated EVGEN file is
caught before the sweep reads it. Needs xrdfs (run inside eic-shell).
"""
import concurrent.futures as cf
import json
import os
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
XROOTD = 'root://dtn2304.jlab.org:8443'


def stat(path):
    r = subprocess.run(['xrdfs', XROOTD, 'stat', path], capture_output=True, text=True, timeout=120)
    kv = dict(l.split(':', 1) for l in r.stdout.splitlines() if ':' in l)
    return {k.strip(): v.strip() for k, v in kv.items()} if r.returncode == 0 else None


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    m = json.load(open(os.path.join(REPO, 'run', sys.argv[1], 'manifest.json')))
    todo = [(p, pin) for d in m['datasets'] for p, pin in zip(d['files'], d['pins'])]
    bad = 0
    with cf.ThreadPoolExecutor(16) as ex:
        for (p, pin), st in zip(todo, ex.map(lambda t: stat(t[0]), todo)):
            why = None
            if st is None:
                why = 'not found'
            elif int(st['Size']) != pin['bytes']:
                why = 'size %s != pinned %d' % (st['Size'], pin['bytes'])
            elif pin.get('mtime') and st['MTime'].replace(' ', 'T') != pin['mtime']:
                why = 'mtime %s != pinned %s' % (st['MTime'], pin['mtime'])
            if why:
                bad += 1
                print('MISMATCH', p, why)
    print('checked %d files, %d mismatches' % (len(todo), bad))
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
