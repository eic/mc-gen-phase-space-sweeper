"""Pick the files the phase-space sweep reads, from the campaign lock file.

Usage (from the repo root):  python3 sweep/resolve.py <campaign>      e.g. 26.07
Reads pins/<campaign>/evgen_inputs.json (from pin_inputs.py) and writes
run/<campaign>/{manifest.json, chunks.txt, in/cNNNN.txt}.

One sweep dataset = one EVGEN Rucio dataset (directory) that the campaign
consumed. From each, up to FILES_PER_DATASET of the pinned files are taken,
spread over the sorted list (first, middle, last), so the choice is a pure
function of the lock file. Chunks hold CHUNK files each; one HTCondor job per chunk.

Each in/ line is '<label>|<path>', label = '<dataset> :: <path below EVGEN/>',
path = the EIC-XRD path that phase_space.py opens over xrootd.
"""
import argparse
import json
import os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PFN_ROOT = '/jlab-osdf-ro/eic/EPIC/cache/EVGEN/'   # LFN epic:/EVGEN/<x> -> PFN_ROOT + <x> on dtn2304
FILES_PER_DATASET = 3
CHUNK = 8


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('campaign')
    a = ap.parse_args()
    lock_path = os.path.join(REPO, 'pins', a.campaign, 'evgen_inputs.json')
    lock = json.load(open(lock_path))
    run = os.path.join(REPO, 'run', a.campaign)
    os.makedirs(os.path.join(run, 'in'), exist_ok=True)

    datasets, lines = [], []
    for did, d in sorted(lock['datasets'].items()):
        name = did.split(':', 1)[1].lstrip('/')                 # EVGEN/DIS/...
        files = sorted(f['lfn'].split(':', 1)[1] for f in d['files'])
        n = len(files)
        pick = sorted({0, n // 2, n - 1})[:FILES_PER_DATASET]
        chosen = [PFN_ROOT + files[i][len('/EVGEN/'):] for i in pick]
        by_lfn = {f['lfn']: f for f in d['files']}
        datasets.append({'dataset': name, 'source': d['source'], 'n_files': n,
                         'files': chosen,
                         'pins': [by_lfn['epic:' + files[i]] for i in pick]})
        lines += ['%s :: %s|%s' % (name, p[len(PFN_ROOT):], p) for p in chosen]

    for old in os.listdir(os.path.join(run, 'in')):
        os.remove(os.path.join(run, 'in', old))
    chunks = [lines[i:i + CHUNK] for i in range(0, len(lines), CHUNK)]
    for i, c in enumerate(chunks):
        with open(os.path.join(run, 'in', 'c%04d.txt' % i), 'w') as fh:
            fh.write('\n'.join(c) + '\n')
    manifest = {'lock': os.path.relpath(lock_path, REPO), 'campaign': lock['campaign'],
                'catalog_sha256': lock['catalog_sha256'], 'files_per_dataset': FILES_PER_DATASET,
                'datasets': datasets}
    json.dump(manifest, open(os.path.join(run, 'manifest.json'), 'w'), indent=1)
    open(os.path.join(run, 'chunks.txt'), 'w').write(''.join('c%04d\n' % i for i in range(len(chunks))))
    print('campaign %s: datasets %d, files %d, chunks %d' % (lock['campaign'], len(datasets), len(lines), len(chunks)))


if __name__ == '__main__':
    main()
