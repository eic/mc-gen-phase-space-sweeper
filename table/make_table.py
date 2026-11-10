"""Build the generators-vs-eta LaTeX table from the sweep results.

Pipeline (per campaign C):
  run/C/out/*.json + run/C/manifest.json --sweep/markers.py--> results/C/latest_markers.json
  results/C/latest_markers.json + table/spec.py --this script--> table/C/generators_eta.tex
  (+ generators_eta.provenance.txt, and generators_eta.pdf/.png if pdflatex is available)

Usage (from the repo root):
  python3 table/make_table.py C              rebuild latest_markers.json, then the table and image
  python3 table/make_table.py C --no-refresh use the existing latest_markers.json
  python3 table/make_table.py C --check      rebuild and fail if the .tex would change

spec.py is shared by all campaigns. A table row whose sources are all absent
from a campaign is dropped (and listed in the provenance file); a source that
is absent from one row of several is ignored for that row.
"""
import argparse
import difflib
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.dont_write_bytecode = True
sys.path.insert(0, HERE)
import spec  # noqa: E402

MARKS = {'●': r'$\bullet$', '○': r'$\circ$', '·': ''}
RANK = {'·': 0, '○': 1, '●': 2}
# Byte-reproducible PDF: no dates, no random trailer ID, no pdfTeX banner.
STANDALONE = r'''\pdfinfoomitdate=1
\pdftrailerid{}
\pdfsuppressptexinfo=-1
\documentclass[twocolumn]{article}
\usepackage[margin=1cm]{geometry}
\usepackage{booktabs,tabularx,caption,amssymb}
\pagestyle{empty}
\begin{document}
\input{%s}
\end{document}
'''


def committed_markers(campaign):
    return os.path.join(REPO, 'results', campaign, 'latest_markers.json')


def load_markers(campaign, refresh, path):
    """Rebuild latest_markers.json from run/<campaign>/out into `path` (if refresh) and load it."""
    if refresh:
        subprocess.run([sys.executable, '-B', os.path.join('sweep', 'markers.py'), campaign, path],
                       cwd=REPO, check=True, stdout=subprocess.DEVNULL)
    return json.load(open(path, encoding='utf-8'))


def key(src):
    return src[0] if isinstance(src, tuple) else src


def label(proc, srcs):
    """Fill '{species}' from the (key, species) sources present, in spec order."""
    sp = []
    for s in srcs:
        if isinstance(s, tuple) and s[1] not in sp:
            sp.append(s[1])
    return proc.replace('{species}', ', '.join(sp))


def validate(data):
    """Every sweep row must be placed in the table or OMITTED (nothing disappears silently).
    Returns the spec sources this campaign has no data for."""
    used = [key(s) for _, rows in spec.GROUPS for _, _, srcs in rows for s in srcs]
    unplaced = sorted(set(data) - set(used) - set(spec.OMITTED))
    if unplaced:
        sys.exit('make_table: new rows in latest_markers.json, add to a row or OMITTED in spec.py: %s' % unplaced)
    return sorted(set(used) - set(data))


def render(data, campaign):
    n = len(spec.COLUMNS)
    L = [r'\par\medskip',
         r'\noindent\begin{minipage}{\columnwidth}',
         r'\centering\footnotesize',
         r'\setlength{\tabcolsep}{2.4pt}',
         r'\captionsetup{font=footnotesize}',
         r'\captionof{table}{%s}' % spec.CAPTION.replace('{campaign}', campaign),
         r'\label{%s}' % spec.LABEL,
         r'\begin{tabularx}{\columnwidth}{@{}l>{\raggedright\arraybackslash}X*{%d}{c}@{}}' % n,
         r'\toprule',
         r'& & \multicolumn{%d}{c}{Region ($\eta$ increases $\rightarrow$)} \\' % n,
         r'\cmidrule(l){3-%d}' % (n + 2),
         'Generator & Process & ' + ' & '.join(spec.HEADERS) + r' \\',
         r'\midrule']
    prov, dropped = ['Campaign %s' % campaign, ''], []
    first = True
    for heading, rows in spec.GROUPS:
        dropped += ['%s | %s' % (g, label(p, srcs)) for g, p, srcs in rows if not any(key(s) in data for s in srcs)]
        rows = [(g, p, [s for s in srcs if key(s) in data]) for g, p, srcs in rows]
        rows = [(g, label(p, srcs), srcs) for g, p, srcs in rows]
        rows = [r for r in rows if r[2]]
        if not rows:
            continue
        if not first:
            L.append(r'\addlinespace[3pt]')
        first = False
        L.append(r'\multicolumn{%d}{@{}l}{\textit{%s}}\\' % (n + 2, heading))
        for gen, proc, srcs in rows:
            marks = [max((data[key(s)][c] for s in srcs), key=RANK.get) for c in spec.COLUMNS]
            L.append('%-14s & %-24s & ' % (gen, proc) + ' & '.join('%-9s' % MARKS[m] for m in marks).rstrip() + r' \\')
            prov.append('%s | %s' % (gen, proc))
            for s in srcs:
                s = key(s)
                d = data[s]
                prov.append('    %-24s v=%-12s n=%-3d ' % (s, d['version'] or '-', len(d['datasets']))
                            + ' '.join('%s=%s%.2f' % (c, d[c], d[c + '_median']) for c in spec.COLUMNS))
    L += [r'\bottomrule', r'\end{tabularx}', '', r'\vspace{3pt}', r'{\scriptsize\raggedright',
          spec.FOOTNOTE, r'\par}', r'\end{minipage}', r'\par\medskip', '']
    prov += ['', 'Rows dropped (no %s data):' % campaign] + ['    ' + d for d in dropped]
    prov += ['', 'Omitted:'] + ['    %-24s %s' % kv for kv in sorted(spec.OMITTED.items())] + ['']
    return '\n'.join(L), '\n'.join(prov)


def render_image(out_dir, tex_path):
    """Compile the table alone to generators_eta.pdf and a 300 dpi generators_eta.png."""
    missing = [t for t in ('pdflatex', 'convert') if not shutil.which(t)]
    if missing:
        sys.exit('make_table: %s not found; the committed .pdf/.png cannot be reproduced without them' % missing)
    with tempfile.TemporaryDirectory() as tmp:
        shutil.copy(tex_path, os.path.join(tmp, 'table.tex'))   # relative input: no host paths in the PDF
        open(os.path.join(tmp, 't.tex'), 'w').write(STANDALONE % 'table.tex')
        env = dict(os.environ, SOURCE_DATE_EPOCH='0', FORCE_SOURCE_DATE='1')
        r = subprocess.run(['pdflatex', '-interaction=nonstopmode', '-halt-on-error', 't.tex'],
                           cwd=tmp, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
        if r.returncode:
            sys.exit('pdflatex failed:\n' + r.stdout[-2000:])
        pdf = os.path.join(out_dir, 'generators_eta.pdf')
        shutil.copy(os.path.join(tmp, 't.pdf'), pdf)
    subprocess.run(['convert', '-density', '300', pdf, '-trim', '-bordercolor', 'white', '-border', '20',
                        '-background', 'white', '-alpha', 'remove', '-strip',
                        '-define', 'png:exclude-chunks=date,time,tEXt,zTXt,iTXt',
                        os.path.join(out_dir, 'generators_eta.png')],
                       check=True, stderr=subprocess.DEVNULL)


OUTPUTS = ('generators_eta.tex', 'generators_eta.provenance.txt', 'generators_eta.pdf', 'generators_eta.png')


def build(campaign, refresh, markers_path, out_dir):
    data = load_markers(campaign, refresh, markers_path)
    validate(data)
    tex, prov = render(data, campaign)
    os.makedirs(out_dir, exist_ok=True)
    tex_path = os.path.join(out_dir, OUTPUTS[0])
    open(tex_path, 'w', encoding='utf-8').write(tex)
    open(os.path.join(out_dir, OUTPUTS[1]), 'w', encoding='utf-8').write(prov)
    render_image(out_dir, tex_path)


def check(campaign):
    """Rebuild everything into a scratch dir; exit 1 unless it is byte-identical to what is committed."""
    committed = [(committed_markers(campaign), 'latest_markers.json')] + \
                [(os.path.join(HERE, campaign, f), f) for f in OUTPUTS]
    with tempfile.TemporaryDirectory() as tmp:
        build(campaign, True, os.path.join(tmp, 'latest_markers.json'), tmp)
        bad = []
        for path, name in committed:
            new = open(os.path.join(tmp, name), 'rb').read()
            old = open(path, 'rb').read() if os.path.exists(path) else b''
            if new != old:
                bad.append(os.path.relpath(path, REPO))
                if not name.endswith(('.pdf', '.png')):
                    sys.stdout.writelines(difflib.unified_diff(old.decode().splitlines(True), new.decode().splitlines(True),
                                                               path, 'regenerated'))
    if bad:
        sys.exit('make_table: not reproduced byte-for-byte: %s' % ', '.join(bad))
    print('reproduced byte-for-byte: %s' % ', '.join(os.path.relpath(p, REPO) for p, _ in committed))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('campaign', help='e.g. 26.07; reads run/<campaign>/out, writes results/<campaign>/ and table/<campaign>/')
    ap.add_argument('--no-refresh', action='store_true', help='use the existing results/<campaign>/latest_markers.json')
    ap.add_argument('--check', action='store_true',
                    help='rebuild into a scratch dir and exit 1 unless every committed output is byte-identical')
    a = ap.parse_args()
    if a.check:
        check(a.campaign)
        return
    build(a.campaign, not a.no_refresh, committed_markers(a.campaign), os.path.join(HERE, a.campaign))
    print('wrote results/%s/latest_markers.json and table/%s/{%s}' % (a.campaign, a.campaign, ','.join(OUTPUTS)))


if __name__ == '__main__':
    main()
