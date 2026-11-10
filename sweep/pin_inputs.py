"""Pin the sweep to the EVGEN files that a production campaign actually consumed.

Source of truth: the PCS campaign catalog (public JSON) and Rucio.
  1. Fetch https://epic-devcloud.org/prod/pcs/api/v1/campaigns/<campaign>/catalog/
     (or read a saved snapshot with --catalog) and save it as pins/<campaign>/catalog.json.
  2. For every non-particle-gun sample with an output dataset (RECO or FULL),
     list the output files in Rucio.
  3. Map each output file to its parent EVGEN file:
       epic:/RECO/<ver>/epic_craterlake/[<bkg>/<..>/<..>/][tryN/]<path>/<stem>.NNNN.eicrecon.edm4eic.root
         -> epic:/EVGEN/<path>/<stem>.<ext>
     and look the parent up in the EVGEN Rucio dataset epic:/EVGEN/<path>.
  4. Write pins/<campaign>/evgen_inputs.json: every EVGEN file that fed at least
     one output, with its Rucio adler32, bytes and event count, plus the samples
     and output files that used it. Unresolved outputs are listed, not dropped.

The lock file is what resolve.py reads; commit it. Re-running this later gives a
different lock only if the campaign produced more outputs (diff it to see).

Run inside eic-shell (needs the rucio client; uses the default read-only
/opt/rucio/etc/rucio.cfg, account eicread):
  printf '%s\n' "unset BEARER_TOKEN BEARER_TOKEN_FILE RUCIO_CONFIG; python3 sweep/pin_inputs.py 26.07" \
      | /gpfs02/eic/rahmans/container/eic-shell
"""
import argparse
import collections
import concurrent.futures as cf
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.request

from rucio.client import Client

CATALOG_URL = 'https://epic-devcloud.org/prod/pcs/api/v1/campaigns/%s/catalog/'
XROOTD = 'root://dtn2304.jlab.org:8443'
XROOTD_BASE = '/jlab-osdf-ro/eic/EPIC/cache'   # EIC-XRD storage prefix for LFN /EVGEN/...
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
USED_STATUS = ('submitted', 'past_output')
AREAS = ('DIS', 'SIDIS', 'DDIS', 'EXCLUSIVE', 'BACKGROUNDS', 'EW_BSM', 'SR')
OUT_PREFIX = re.compile(r'^/(RECO|FULL)/[^/]+/[^/]+/')
# Output names append numeric fields to the EVGEN stem: .NNNN, .NNNNN, .<pandaid>.NNNN or .NNNN.p<pandaid>
OUT_SUFFIX = re.compile(r'(\.p?\d+)+\.(eicrecon\.edm4eic|edm4hep)\.root$')
EVGEN_EXT = re.compile(r'\.(hepmc3\.tree\.root|hepmc3?(\.gz)?|hepmc\.ab)$')


def evgen_dataset_of(output_did):
    """epic:/RECO/26.07.1/epic_craterlake/try2/DIS/NC/... -> /EVGEN/DIS/NC/..."""
    rel = OUT_PREFIX.sub('', output_did.split(':', 1)[1])
    segs = rel.split('/')
    while segs and segs[0] not in AREAS:   # drops tryN/ and Bkg_<mix>/<..>/<..>/
        segs = segs[1:]
    return '/EVGEN/' + '/'.join(segs) if segs else None


def xrootd_files(name):
    """Fallback for EVGEN directories that were never registered in Rucio: list them on
    EIC-XRD. Size and mtime are recorded; xrootd here cannot return checksums."""
    r = subprocess.run(['xrdfs', XROOTD, 'ls', '-l', XROOTD_BASE + name], capture_output=True, text=True, timeout=300)
    if r.returncode:
        raise RuntimeError('xrdfs ls: ' + (r.stderr.strip().splitlines() or ['rc %d' % r.returncode])[-1])
    fs = []
    for line in r.stdout.splitlines():
        p = line.split()
        if len(p) >= 7 and p[0].startswith('-'):
            fs.append({'name': p[6][len(XROOTD_BASE):], 'bytes': int(p[3]), 'mtime': p[4] + 'T' + p[5],
                       'adler32': None, 'events': None})
    return fs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('campaign')
    ap.add_argument('--catalog', help='saved catalog JSON instead of fetching')
    ap.add_argument('--threads', type=int, default=16)
    a = ap.parse_args()
    out_dir = os.path.join(HERE, 'pins', a.campaign)
    os.makedirs(out_dir, exist_ok=True)

    raw = open(a.catalog, 'rb').read() if a.catalog else urllib.request.urlopen(CATALOG_URL % a.campaign, timeout=120).read()
    cat = json.loads(raw)
    with open(os.path.join(out_dir, 'catalog.json'), 'wb') as fh:
        fh.write(raw)

    outputs = collections.defaultdict(set)   # output DID -> samples
    for s in cat['samples']:
        if s['status'] not in USED_STATUS or s['tags']['physics']['parameters'].get('process') == 'SINGLE':
            continue
        for o in s['outputs']:
            if '/SINGLE/' not in o['did']:
                outputs[o['did']].add(s['sample'])

    c = Client()

    def files_of(did):
        scope, name = did.split(':', 1)
        err = None
        for _ in range(4):
            try:
                return did, list(c.list_files(scope, name)), None
            except Exception as e:  # noqa: BLE001 - recorded, not fatal
                err = '%s: %s' % (type(e).__name__, str(e).splitlines()[0])
                if 'DataIdentifierNotFound' in err:
                    break
        if name.startswith('/EVGEN/') and 'DataIdentifierNotFound' in err:
            try:
                return did, [dict(f, source='xrootd') for f in xrootd_files(name)], None
            except Exception as e:  # noqa: BLE001
                err += '; ' + str(e)
        return did, [], err

    with cf.ThreadPoolExecutor(a.threads) as ex:
        out_files = {d: (fs, err) for d, fs, err in ex.map(files_of, sorted(outputs))}
        evgen_dids = sorted({'epic:' + e for e in map(evgen_dataset_of, outputs) if e})
        evgen_files = {d: (fs, err) for d, fs, err in ex.map(files_of, evgen_dids)}

    by_stem = {}  # (evgen dataset, stem) -> rucio file record
    for d, (fs, _) in evgen_files.items():
        for f in fs:
            base = f['name'].rsplit('/', 1)[1]
            by_stem.setdefault((d, EVGEN_EXT.sub('', base)), []).append(f)

    pinned = {}       # evgen LFN -> record
    unresolved = []
    for did, (fs, err) in sorted(out_files.items()):
        ev = evgen_dataset_of(did)
        if err or not ev:
            unresolved.append({'output_dataset': did, 'reason': err or 'no EVGEN area in path'})
            continue
        evd = 'epic:' + ev
        if evgen_files[evd][1]:
            unresolved.append({'output_dataset': did, 'reason': 'EVGEN dataset %s: %s' % (evd, evgen_files[evd][1])})
            continue
        for f in fs:
            stem = OUT_SUFFIX.sub('', f['name'].rsplit('/', 1)[1])
            cands = by_stem.get((evd, stem), [])
            if len(cands) > 1:   # same stem in several formats: prefer the ROOT tree
                cands = [x for x in cands if x['name'].endswith('.hepmc3.tree.root')] or cands
            if len(cands) != 1:
                unresolved.append({'output_dataset': did, 'output_file': f['name'],
                                   'reason': 'parent %s/%s.* %s' % (ev, stem, 'not in EVGEN dataset' if not cands else 'ambiguous')})
                continue
            p = cands[0]
            r = pinned.setdefault(p['name'], {'lfn': 'epic:' + p['name'], 'evgen_dataset': evd,
                                              'adler32': p['adler32'], 'bytes': p['bytes'], 'events': p.get('events'),
                                              'source': p.get('source', 'rucio'), 'mtime': p.get('mtime'),
                                              'samples': set(), 'output_datasets': set(), 'n_output_files': 0})
            r['samples'] |= outputs[did]
            r['output_datasets'].add(did)
            r['n_output_files'] += 1

    datasets = collections.defaultdict(lambda: {'samples': set(), 'output_datasets': set(), 'files': []})
    for r in pinned.values():
        d = datasets[r.pop('evgen_dataset')]
        d['samples'] |= r.pop('samples')
        d['output_datasets'] |= r.pop('output_datasets')
        d['files'].append(r)
    lock = {
        'campaign': a.campaign,
        'catalog_url': CATALOG_URL % a.campaign,
        'catalog_generated_at': cat.get('generated_at'),
        'catalog_sha256': hashlib.sha256(raw).hexdigest(),
        'rule': 'EVGEN files that are the parent of >=1 RECO/FULL output file of a non-particle-gun '
                'sample with status in %s' % (USED_STATUS,),
        'n_output_datasets': len(outputs),
        'n_evgen_datasets': len(datasets),
        'n_evgen_files': len(pinned),
        'datasets': {d: {'n_files_available': len(evgen_files[d][0]),
                         'source': v['files'][0]['source'],
                         'samples': sorted(v['samples']),
                         'output_datasets': sorted(v['output_datasets']),
                         'files': sorted(v['files'], key=lambda r: r['lfn'])} for d, v in sorted(datasets.items())},
        'unresolved': unresolved,
    }
    json.dump(lock, open(os.path.join(out_dir, 'evgen_inputs.json'), 'w'), indent=1, sort_keys=False)
    print('output datasets %d -> EVGEN datasets %d, files %d; unresolved entries %d'
          % (len(outputs), len(datasets), len(pinned), len(unresolved)), file=sys.stderr)


if __name__ == '__main__':
    main()
