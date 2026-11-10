"""Map each generator's final-state particles onto ePIC detector regions.

Run inside eic_xl (uproot, awkward, numpy). Input: a file of lines
'<label>|<xrootd path or local path>'. Output: JSON on stdout.

Regions (approximate acceptances, ePIC pre-TDR v3.1):
  central detector by pseudorapidity about the detector (electron-beam) axis:
    far_backward  eta < -3.5   (beam-pipe region: low-Q2 tagger / luminosity)
    backward      -3.5 <= eta < -1.5
    barrel        -1.5 <= eta <= 1.5
    forward       1.5 < eta <= 3.5
  beyond eta > 3.5, by the angle theta_h to the outgoing hadron beam axis
  (taken from the file's own hadron beam particle, so the crossing angle is
  whatever the afterburner applied):
    B0            5.5 <= theta_h < 20 mrad (charged or neutral)
    ZDC           neutral, theta_h < 4.5 mrad
    RP            charged, theta_h < 5 mrad, rigidity ratio > 0.6 (Roman pots)
    OMD           charged, theta_h < 5 mrad, 0.25 < rigidity ratio <= 0.6
    in_beam       ions with A > 4 inside 5 mrad (nuclear remnant stays with beam)
    ff_gap        anything else beyond eta 3.5 (between acceptances)
  invisible       neutrinos
"""
import json
import sys

import awkward as ak
import numpy as np
import uproot

N_EVENTS = 2000
REGIONS = ['far_backward', 'backward', 'barrel', 'forward', 'B0', 'RP', 'OMD',
           'ZDC', 'in_beam', 'ff_gap', 'invisible']

CHARGE = {11: -1, 13: -1, 15: -1, 211: 1, 321: 1, 2212: 1, 3222: 1, 3112: -1,
          3312: -1, 3334: -1, 411: 1, 431: 1, 4122: 1, 24: 1, 521: 1, 4222: 2,
          4212: 1, 1000010020: 1, 1000010030: 1, 1000020030: 2, 1000020040: 2}
NEUTRAL = {22, 111, 130, 310, 2112, 3122, 3212, 3322, 421, 12, 14, 16, 113,
           221, 223, 331, 333, 443, 553, 511, 4132, 0}
NEUTRINO = {12, 14, 16}


def ion_za(pid):
    a = abs(pid)
    if a >= 1000000000:
        return (a // 10000) % 1000, (a // 10) % 1000
    return None


def charge_of(pid):
    za = ion_za(pid)
    if za:
        return za[0]
    a = abs(pid)
    if a in CHARGE:
        return CHARGE[a] * (1 if pid > 0 else -1)
    if a in NEUTRAL:
        return 0
    return None


def mass_number(pid):
    za = ion_za(pid)
    if za:
        return za[1]
    return 1 if abs(pid) in (2212, 2112) else 0


# Nuclear species named in dataset paths (eAu, eHe3, ...): (A, Z).
NUCLEI = {'H2': (2, 1), 'D': (2, 1), 'He3': (3, 2), 'He4': (4, 2), 'Li7': (7, 3),
          'C': (12, 6), 'C12': (12, 6), 'O': (16, 8), 'O16': (16, 8), 'Ca': (40, 20),
          'Ca40': (40, 20), 'Cu': (63, 29), 'Cu63': (63, 29), 'Ru': (96, 44),
          'Ru96': (96, 44), 'Ag': (107, 47), 'Ag107': (107, 47), 'Xe': (131, 54),
          'Au': (197, 79), 'Au197': (197, 79), 'Pb': (208, 82), 'Pb208': (208, 82),
          'U': (238, 92), 'U238': (238, 92)}


def species_a_over_z(label):
    import re
    for tok in re.findall(r'(?<![A-Za-z])e([A-Z][a-z]?\d*)(?![a-z])', label):
        if tok in NUCLEI:
            a, z = NUCLEI[tok]
            return a / z
    return 1.0


def read_ascii(path):
    """HepMC2/3 ASCII (optionally gzipped, local or root://) -> awkward arrays."""
    import gzip
    import io
    if path.startswith('root://'):
        import subprocess
        import tempfile
        tmp = tempfile.NamedTemporaryFile(delete=False)
        subprocess.run(['xrdcp', '-s', '-f', path, tmp.name], check=True)
        path = tmp.name
    opener = gzip.open if path.endswith('.gz') else open
    pid, st, px, py, pz, e = [], [], [], [], [], []
    cur = None
    v3 = None
    with opener(path, 'rt') as fh:
        for line in fh:
            if line.startswith('HepMC::Version'):
                v3 = line.split()[1].startswith('3')
            if line.startswith('E '):
                if cur is not None and len(pid) >= N_EVENTS:
                    break
                cur = [[], [], [], [], [], []]
                for lst, c in zip((pid, st, px, py, pz, e), cur):
                    lst.append(c)
            elif line.startswith('P ') and cur is not None:
                f = line.split()
                if v3:   # P id parent pid px py pz e m status
                    vals = (int(f[3]), int(f[9]), f[4], f[5], f[6], f[7])
                else:    # P barcode pid px py pz e m status ...
                    vals = (int(f[2]), int(f[8]), f[3], f[4], f[5], f[6])
                for c, v in zip(cur, vals):
                    c.append(float(v) if isinstance(v, str) else v)
    return {k: ak.Array(v[:N_EVENTS]) for k, v in zip(('pid', 'status', 'm_v1', 'm_v2', 'm_v3', 'm_v4'), (pid, st, px, py, pz, e))}


def analyse(label, path):
    if not path.endswith('.root'):
        return analyse_arrays(label, path, read_ascii(path))
    f = uproot.open(path)
    tname = sorted(k for k in f.keys() if k.startswith('hepmc3_tree'))[-1]
    t = f[tname]
    pre = 'hepmc3_event/particles/particles.'
    arr = t.arrays([pre + 'pid', pre + 'status', pre + 'momentum.m_v1',
                    pre + 'momentum.m_v2', pre + 'momentum.m_v3', pre + 'momentum.m_v4'],
                   entry_stop=N_EVENTS, library='ak')
    return analyse_arrays(label, path, {'pid': arr[pre + 'pid'], 'status': arr[pre + 'status'],
                                        'm_v1': arr[pre + 'momentum.m_v1'], 'm_v2': arr[pre + 'momentum.m_v2'],
                                        'm_v3': arr[pre + 'momentum.m_v3'], 'm_v4': arr[pre + 'momentum.m_v4']})


def analyse_arrays(label, path, a):
    pid, st = a['pid'], a['status']
    px, py, pz, e = a['m_v1'], a['m_v2'], a['m_v3'], a['m_v4']
    nev = len(pid)

    # Beams (status 4): hadron beam has pz > 0.
    beam = st == 4
    hb = (pz > 0) & beam
    hpx, hpy, hpz = ak.flatten(px[hb]), ak.flatten(py[hb]), ak.flatten(pz[hb])
    hpid = ak.flatten(pid[hb])
    if len(hpz) == 0:
        # No status-4 hadron beam recorded: take the per-nucleon energy from
        # the dataset path (<E_e>x<E_h>) and an IP6 proton direction.
        import re
        m = re.search(r'(\d+(?:\.\d+)?)x(\d+(?:\.\d+)?)', label)
        if not m:
            raise RuntimeError('no hadron beam particle and no beam energies in path')
        eh = float(m.group(2))
        hpx, hpy, hpz = np.array([eh * np.sin(-0.025)]), np.array([0.0]), np.array([eh * np.cos(-0.025)])
        hpid = np.array([2212])
    # Per-nucleon hadron beam momentum from the file; the outgoing hadron
    # axis is the IP6 one (-25 mrad in x-z), which every afterburned file
    # here reports, and is fixed so files whose pz>0 "beam" is not the
    # hadron (MadGraph's photon) are treated alike.
    hp_file = float(np.linalg.norm([np.mean(hpx), np.mean(hpy), np.mean(hpz)]))
    bpid = int(hpid[0])
    za = ion_za(bpid)
    hp = hp_file / za[1] if (za and hp_file > 1000) else hp_file
    hdir = np.array([np.sin(-0.025), 0.0, np.cos(-0.025)])
    A_over_Z = species_a_over_z(label)
    beam_rigidity = hp * A_over_Z
    epb = ak.flatten(e[(pz < 0) & beam])
    e_beam = float(np.mean(epb)) if len(epb) else float('nan')

    fs = st == 1
    fpid = ak.to_numpy(ak.flatten(pid[fs]))
    fx, fy, fz = (ak.to_numpy(ak.flatten(v[fs])) for v in (px, py, pz))
    fe = ak.to_numpy(ak.flatten(e[fs]))
    evt = ak.to_numpy(ak.flatten(ak.local_index(pid, axis=0)[:, None] * ak.ones_like(pid[fs])))
    p = np.sqrt(fx ** 2 + fy ** 2 + fz ** 2)
    pt = np.hypot(fx, fy)
    with np.errstate(divide='ignore', invalid='ignore'):
        eta = np.arcsinh(np.where(pt > 0, fz / pt, np.sign(fz) * 1e9))
        cos_h = (fx * hdir[0] + fy * hdir[1] + fz * hdir[2]) / p
    th = np.arccos(np.clip(cos_h, -1, 1)) * 1e3  # mrad

    region = np.empty(len(fpid), dtype=object)
    unknown = set()
    for i, (q_pid, et, thh, pp) in enumerate(zip(fpid, eta, th, p)):
        a = abs(int(q_pid))
        if a in NEUTRINO:
            region[i] = 'invisible'
            continue
        q = charge_of(int(q_pid))
        if q is None:
            unknown.add(int(q_pid))
            q = 1
        if et < -3.5:
            region[i] = 'far_backward'
        elif et < -1.5:
            region[i] = 'backward'
        elif et <= 1.5:
            region[i] = 'barrel'
        elif et <= 3.5:
            region[i] = 'forward'
        elif 5.5 <= thh < 20:
            region[i] = 'B0'
        elif q == 0 and thh < 4.5:
            region[i] = 'ZDC'
        elif q != 0 and thh < 5:
            if mass_number(int(q_pid)) > 4:
                region[i] = 'in_beam'
            else:
                r = (pp / abs(q)) / beam_rigidity
                region[i] = 'RP' if r > 0.6 else ('OMD' if r > 0.25 else 'ff_gap')
        else:
            region[i] = 'ff_gap'

    # Scattered electron: the final-state e- with the most negative pz.
    ele = fpid == 11
    scat = {}
    best = {}
    for i in np.nonzero(ele)[0]:
        ev = evt[i]
        if ev not in best or fz[i] < fz[best[ev]]:
            best[ev] = i
    for ev, i in best.items():
        scat[region[i]] = scat.get(region[i], 0) + 1
    n_no_e = nev - len(best)

    mult = {r: float(np.sum(region == r)) / nev for r in REGIONS}
    occ = {}
    for r in REGIONS:
        occ[r] = float(len(set(evt[region == r]))) / nev
    # Species of interest far forward
    ff_species = {}
    for r in ('B0', 'RP', 'OMD', 'ZDC', 'in_beam'):
        sel = region == r
        if sel.any():
            vals, cnt = np.unique(fpid[sel], return_counts=True)
            order = np.argsort(-cnt)[:4]
            ff_species[r] = {str(int(vals[j])): round(float(cnt[j]) / nev, 3) for j in order}
    eta_hist, edges = np.histogram(eta[np.isfinite(eta)], bins=np.arange(-8, 8.01, 0.5))
    return {
        'label': label, 'path': path, 'events': nev, 'A_over_Z': A_over_Z,
        'beam': {'e_energy': round(e_beam, 2), 'hadron_pid': bpid,
                 'hadron_p_per_nucleon': round(float(hp), 2), 'beam_A_over_Z': round(A_over_Z, 3),
                 'file_hadron_axis_mrad': round(float(np.arctan2(np.mean(hpx), np.mean(hpz)) * 1e3), 2)},
        'mean_multiplicity': mult, 'event_occupancy': occ,
        'scattered_electron': {k: round(v / nev, 4) for k, v in scat.items()},
        'no_final_state_electron': round(n_no_e / nev, 4),
        'far_forward_species_per_event': ff_species,
        'eta_hist': eta_hist.tolist(), 'eta_edges': edges.tolist(),
        'unknown_pids': sorted(unknown)[:20],
    }


def main():
    out = []
    for line in open(sys.argv[1]):
        line = line.strip()
        if not line or '|' not in line:
            continue
        label, path = line.split('|', 1)
        if not path:
            continue
        if path.startswith('/jlab-osdf-ro'):
            path = 'root://dtn2304.jlab.org:8443/' + path
        try:
            out.append(analyse(label, path))
            print('ok', label, file=sys.stderr)
        except Exception as exc:  # report and continue
            out.append({'label': label, 'path': path, 'error': repr(exc)})
            print('FAIL', label, exc, file=sys.stderr)
    json.dump(out, sys.stdout, indent=1)


if __name__ == '__main__':
    main()
