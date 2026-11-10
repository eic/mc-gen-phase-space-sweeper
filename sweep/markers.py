"""Per-configuration eta-region markers from the sweep, latest sample only.

Reads run/<campaign>/manifest.json and run/<campaign>/out/*.json (the sweep
output) and writes results/<campaign>/latest_markers.json, which
table/make_table.py turns into the table.

A row is a generator + target species (+ process). Within a row only the
datasets carrying the highest generator version are kept (e.g. BeAGLE
1.03.02-3.1 > 1.03.02-2.0); unversioned datasets are dropped when a versioned
one exists. Only .hepmc3.tree.root files are used; TCS and backgrounds are
excluded.

Columns (mean particles per event, event-weighted over a dataset's files):
  fb   eta < -3.5      scattered electron (low-Q2 tagger)
  bwd  -3.5 .. -1.5    all final-state particles
  bar  -1.5 .. 1.5     all final-state particles
  fwd  1.5 .. 3.5      all final-state particles
  b0   ~4.6 .. 5.9     p, Lambda, light nuclei
  far  > ~6            p, light nuclei (Roman pots, off-momentum); n, Lambda (ZDC)
Marker per row: ● if the median dataset has >= 0.5, ○ if the median has
>= 0.1 or a quarter of the datasets reach 0.5, · otherwise.

Usage: python3 sweep/markers.py <campaign> [output path]   (from the repo root;
       default output results/<campaign>/latest_markers.json)
"""
import glob
import json
import os
import re
import statistics as st
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = '/jlab-osdf-ro/eic/EPIC/cache/EVGEN/'   # must match sweep/resolve.py PFN_ROOT
COLS = ('fb', 'bwd', 'bar', 'fwd', 'b0', 'far')
CHARGED_FF = {2212, 3122, 1000010020, 1000010030, 1000020030, 1000020040}
NEUTRAL_FF = {2112, 3122}

# Generator attribution from dataset/file paths; first match wins.
FAMILIES = [
    ('Background: Xsuite e-beam-gas', r'EIC_ESR_Xsuite|BEAMGAS/electron/(brems|coulomb|touschek)|electron_(brems|coulomb|touschek)'),
    ('Background: proton beam-gas', r'BEAMGAS/proton'), ('Background: merged', r'MERGED|bgmerged|merged_lowstat|HEPMC_merger'),
    ('Background: GETaLM', r'GETaLM'), ('Background: synchrotron radiation', r'SYNRAD|synrad|/SR/'),
    ('TCSGen', r'TCS_gen'),
    ('Not recorded: u-channel meson', r'uChannel|UCHANNEL|u_omega'),
    ('Not recorded: older DVCS', r'DVCS_ABCONV/(10x100|18x275|5x41)/DVCS\.|DVCSD|DVCS-eD'),
    ('Not recorded: Upsilon threshold/photoproduction', r'upsilon1s(_threshold|photo)|upsilon[23]sphoto'),
    ('Not recorded: spectroscopy', r'SPECTROSCOPY'),
    ('Not recorded: Lambda SIDIS', r'Lambda_ABCONV/hepmc_Lambda'),
    ('HFsim (BeAGLE)', r'HFsim-BeAGLE'), ('HFsim (PYTHIA 8)', r'HFsim-PYTHIA'),
    ('PYTHIA6-LHAPDF', r'PYTHIA6-LHAPDF|EPPS16'),
    ('BeAGLE', r'BeAGLE'), ('Sartre', r'[Ss]artre'), ('EpIC', r'EpIC'), ('lAger', r'[lL][aA]ger'),
    ('eSTARlight', r'eSTARlight|/slight|slight_'), ('DEMPgen', r'DEMP'), ('eicMesonSFGen', r'MesonSF'),
    ('RAPGAP', r'rapgap'), ('DJANGOH', r'DJANGOH|Djangoh|djangoh'), ('MadGraph5', r'madgraph'),
    ('PYTHIA 6 eic', r'pythia6'), ('PYTHIA 8', r'pythia8'),
]
EXCLUDED = ('Background:', 'TCSGen', 'Not recorded:')

VERSION = re.compile(r'(?:pythia8\.|pythia6-eic/|pythia6\.|BeAGLE|EpIC_?v?|DEMPgen-|lAger|sartre|eSTARlight|'
                     r'DJANGOH|rapgap|eicMesonSFGen-|madgraph5-)(\d[\d.]*(?:-\d[\d.]*)?)', re.I)
SPECIES = re.compile(r'(?<![A-Za-z])e(Au|Ag|Cu|Ru|Ca|Pb|D|H2|He3)(?=[/_]|\d)')


def family(text):
    return next((name for name, rx in FAMILIES if re.search(rx, text)), None)


def version(text):
    vs = [tuple(int(x) for x in re.split(r'[.-]', m.group(1)) if x) for m in VERSION.finditer(text)]
    return max(vs) if vs else ()


def row_of(text, gen):
    sp = SPECIES.search(text)
    sp = {'H2': 'D'}.get(sp.group(1), sp.group(1)) if sp else 'p'
    if gen in ('BeAGLE', 'HFsim (BeAGLE)'):
        proc = 'incoh VM' if 'DIFFRACTIVE' in text else ('charm' if 'HFsim' in gen else 'DIS')
        return 'BeAGLE e%s %s' % (sp, proc)
    if gen == 'HFsim (PYTHIA 8)':
        return 'PYTHIA 8 charm'
    if gen == 'PYTHIA 6 eic':
        return 'PYTHIA 6 eic SIDIS' if 'pythia6-eic' in text else 'PYTHIA 6.428 (legacy)'
    if gen == 'DJANGOH':
        return 'DJANGOH ' + ('CC' if '/CC/' in text or '_CC_' in text else 'NC')
    if gen == 'Sartre' and sp != 'p':
        vm = next((m for m in ('phi', 'rho', 'jpsi') if m in text.lower()),
                  'DDIS' if 'ddis' in text.lower() else 'vm')
        return 'Sartre e%s %s' % (sp, vm)
    if gen in ('eSTARlight', 'PYTHIA6-LHAPDF') and sp != 'p':
        return '%s e%s' % (gen, sp)
    if gen == 'DEMPgen':
        return 'DEMPgen pi+n' if re.search(r'pi\+|_pi', text) else 'DEMPgen K+Lambda'
    if gen == 'EpIC':
        return 'EpIC ' + next((p for p in ('DDVCS', 'DVMP', 'DVCS') if p in text), 'other')
    return gen


def region_values(x):
    m = x['mean_multiplicity']
    sp = x.get('far_forward_species_per_event', {})
    b0 = sum(v for p, v in sp.get('B0', {}).items() if int(p) in CHARGED_FF)
    far = (sum(v for r in ('RP', 'OMD') for p, v in sp.get(r, {}).items() if int(p) in CHARGED_FF)
           + sum(v for p, v in sp.get('ZDC', {}).items() if int(p) in NEUTRAL_FF))
    return {'fb': x['scattered_electron'].get('far_backward', 0), 'bwd': m['backward'],
            'bar': m['barrel'], 'fwd': m['forward'], 'b0': b0, 'far': far}


def load_results(run):
    """Sweep outputs keyed by label; retry chunks (run/<campaign>/out/r_*.json) override originals."""
    res = {}
    for f in sorted(glob.glob(os.path.join(run, 'out', 'c*.json'))) + sorted(glob.glob(os.path.join(run, 'out', 'r_*.json'))):
        try:
            for x in json.load(open(f)):
                res[x['label']] = x
        except ValueError:
            print('skipping unreadable', f)
    return res


def main():
    if len(sys.argv) not in (2, 3):
        sys.exit(__doc__)
    campaign = sys.argv[1]
    run = os.path.join(REPO, 'run', campaign)
    res = load_results(run)
    rows = {}
    for ds in json.load(open(os.path.join(run, 'manifest.json')))['datasets']:
        files = [f for f in ds['files'] if f.endswith('.hepmc3.tree.root')]
        if not files or 'TCS' in ds['dataset']:
            continue
        text = ds['dataset'] + ' ' + ' '.join(files)
        gen = family(text)
        if gen is None or gen.startswith(EXCLUDED):
            continue
        xs = [res.get(ds['dataset'] + ' :: ' + f[len(ROOT):]) for f in files]
        xs = [x for x in xs if x and 'error' not in x and x['events'] > 0]
        if not xs:
            continue
        n = sum(x['events'] for x in xs)
        v = {c: sum(region_values(x)[c] * x['events'] for x in xs) / n for c in COLS}
        rows.setdefault(row_of(text, gen), []).append((version(text), ds['dataset'], v))

    out = {}
    for k, items in sorted(rows.items()):
        latest = max(i[0] for i in items)
        keep = [i for i in items if i[0] == latest]
        o = {'version': '.'.join(map(str, latest)), 'datasets': [i[1] for i in keep],
             'dropped_older': len(items) - len(keep)}
        for c in COLS:
            a = [i[2][c] for i in keep]
            med = st.median(a)
            frac = sum(t >= 0.5 for t in a) / len(a)
            o[c] = '●' if med >= 0.5 else ('○' if (med >= 0.1 or frac >= 0.25) else '·')
            o[c + '_median'] = round(med, 3)
        out[k] = o
    path = sys.argv[2] if len(sys.argv) == 3 else os.path.join(REPO, 'results', campaign, 'latest_markers.json')
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    json.dump(out, open(path, 'w'), ensure_ascii=False, indent=1)
    print('wrote %s: %d rows' % (path, len(out)))


if __name__ == '__main__':
    main()
