"""Reproduce a campaign's committed outputs from its lock file and compare byte-for-byte.

Usage (from the repo root, on a node with singularity + /cvmfs, xrootd access to dtn2304):
  python3 sweep/reproduce.py <campaign> [--jobs 4] [--chunks c0000,c0007]

Steps, each compared with the committed copy:
  1. resolve.py on pins/<campaign>/evgen_inputs.json -> run/<campaign>/{manifest.json, chunks.txt, in/}
  2. every chunk (or --chunks) through sweep/run.sh into a scratch dir -> out/cNNNN.json
  3. table/make_table.py <campaign> --check (latest_markers.json, .tex, provenance, .pdf, .png)
Exits non-zero at the first step that differs. The committed tree is never modified.

Not covered: pin_inputs.py. The lock is the pin. Re-pinning queries the live
catalog and Rucio, which change while a campaign is still producing, so a
re-pin is a deliberate update (review it with git diff pins/), not a reproduction.
"""
import argparse
import concurrent.futures as cf
import filecmp
import os
import shutil
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('campaign')
    ap.add_argument('--jobs', type=int, default=4)
    ap.add_argument('--chunks', help='comma-separated subset of chunks (default: all)')
    a = ap.parse_args()
    run = os.path.join(REPO, 'run', a.campaign)

    with tempfile.TemporaryDirectory() as tmp:
        # 1. file selection: resolve into a scratch copy of the repo layout
        scratch = os.path.join(tmp, 'repo')
        os.makedirs(os.path.join(scratch, 'pins'))
        shutil.copytree(os.path.join(REPO, 'sweep'), os.path.join(scratch, 'sweep'))
        os.symlink(os.path.join(REPO, 'pins', a.campaign), os.path.join(scratch, 'pins', a.campaign))
        subprocess.run([sys.executable, '-B', 'sweep/resolve.py', a.campaign], cwd=scratch, check=True,
                       stdout=subprocess.DEVNULL)
        srun = os.path.join(scratch, 'run', a.campaign)
        for f in ('manifest.json', 'chunks.txt'):
            if not filecmp.cmp(os.path.join(srun, f), os.path.join(run, f), shallow=False):
                sys.exit('reproduce: run/%s/%s differs from resolve.py output' % (a.campaign, f))
        print('1. resolve: manifest.json and chunks.txt identical')

        # 2. sweep: rerun chunks with the committed run.sh/phase_space.py, outputs into the scratch run dir
        chunks = a.chunks.split(',') if a.chunks else open(os.path.join(run, 'chunks.txt')).read().split()

        def one(c):
            work = os.path.join(tmp, 'work', c)
            os.makedirs(work)
            r = subprocess.run(['bash', os.path.join(scratch, 'sweep', 'run.sh'), a.campaign, c, scratch],
                               env=dict(os.environ, _CONDOR_SCRATCH_DIR=work),
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
            same = r.returncode == 0 and filecmp.cmp(os.path.join(srun, 'out', c + '.json'),
                                                     os.path.join(run, 'out', c + '.json'), shallow=False)
            return c, r.returncode, same, r.stdout[-500:]

        bad = []
        with cf.ThreadPoolExecutor(a.jobs) as ex:
            for c, rc, same, log in ex.map(one, chunks):
                if not same:
                    bad.append(c)
                    print('   %s: %s %s' % (c, 'rc=%d' % rc if rc else 'output differs', log.strip()))
        if bad:
            sys.exit('reproduce: %d of %d chunks not reproduced: %s' % (len(bad), len(chunks), ','.join(bad)))
        print('2. sweep: %d chunks byte-identical' % len(chunks))

    # 3. markers + table from the committed outputs
    r = subprocess.run([sys.executable, '-B', 'table/make_table.py', a.campaign, '--check'], cwd=REPO)
    if r.returncode:
        sys.exit('reproduce: table step not reproduced')
    print('3. table: byte-identical')


if __name__ == '__main__':
    main()
