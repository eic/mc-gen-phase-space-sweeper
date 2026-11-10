r"""What the generators-vs-eta table shows. Edit this file, not the .tex.

Each row names one or more `sources`: keys of results/<campaign>/latest_markers.json.
`{campaign}` in CAPTION is replaced by the campaign name.
A row that merges several sources shows, per column, the strongest marker
among them (● beats ○ beats blank), i.e. "some configuration in this row
reaches the region".

Every key in latest_markers.json must appear either in a row's sources or
in OMITTED, so a new sample in the sweep can never silently disappear.
"""

COLUMNS = ('fb', 'bwd', 'bar', 'fwd', 'b0', 'far')       # keys in latest_markers.json
HEADERS = ('FB', 'Bwd', 'Bar', 'Fwd', 'B0', 'FF')        # printed column names

CAPTION = (r"Where each generator's particles end up in pseudorapidity $\eta$, for the "
           r"\emph{latest} sample of each configuration produced in the {campaign} campaign. "
           r"$\bullet$: median sample has at least 0.5 particles per event; "
           r"$\circ$: median at least 0.1, or at least 0.5 in a quarter of the samples.")
LABEL = 'tab:generators-eta'

# (group heading, [(generator, process, [sources]), ...])
# A source is a latest_markers.json key, or (key, species) for rows covering
# several ions. '{species}' in the process label is filled with the species of
# the sources the campaign actually has, so a label never names an ion that has
# no sample (e.g. 26.07 has Sartre eAu but not eCa).
GROUPS = [
    (r'Basic collisions ($e$+$p$)', [
        ('PYTHIA8',     r'Standard $ep$',       ['PYTHIA 8']),
        ('PYTHIA6-EIC', r'SIDIS',               ['PYTHIA 6 eic SIDIS']),
        ('DJANGOH',     r'With QED radiation',  ['DJANGOH NC']),
    ]),
    (r'Proton stays intact', [
        ('RAPGAP',      r'Diffraction',         ['RAPGAP']),
        ('EpIC',        r'DVCS',                ['EpIC DVCS']),
        ('lAger',       r'$J/\psi$',            ['lAger']),
        ('eSTARlight',  r'$J/\psi$, $\Upsilon$ photoproduction', ['eSTARlight']),
    ]),
    (r'Pion and kaon structure', [
        ('DEMPgen',       r'Pion form factor',  ['DEMPgen pi+n']),
        ('eicMesonSFGen', r'Kaon structure',    ['eicMesonSFGen']),
    ]),
    (r'Light ions', [
        ('BeAGLE', r'$e$D: neutron structure',  ['BeAGLE eD DIS']),
        ('BeAGLE', r'$e\,^3$He: neutron spin',  ['BeAGLE eHe3 DIS']),
    ]),
    (r'Heavy ions: nuclear fragments', [
        ('BeAGLE', r'$e$Au: DIS',                   ['BeAGLE eAu DIS']),
        ('BeAGLE', r'{species}: incoherent VM',
         [('BeAGLE eCa incoh VM', r'$e$Ca'), ('BeAGLE ePb incoh VM', r'$e$Pb')]),
    ]),
    (r'Heavy ions: no fragments, no residual nucleus', [
        ('BeAGLE',     r'$e$Au: charm',          ['BeAGLE eAu charm']),
        ('BeAGLE',     r'$e$Au: incoherent VM',  ['BeAGLE eAu incoh VM']),
        ('BeAGLE',     r'$e$Ag: DIS',            ['BeAGLE eAg DIS']),
        ('BeAGLE',     r'{species}: DIS',        [('BeAGLE eCu DIS', r'$e$Cu'), ('BeAGLE eRu DIS', r'$e$Ru')]),
        ('PY6-LHAPDF', r'{species}: nPDF only',
         [('PYTHIA6-LHAPDF eAu', r'$e$Au'), ('PYTHIA6-LHAPDF eAg', r'$e$Ag')]),
    ]),
    (r'Heavy ions: no fragments, residual nucleus', [
        ('SARTRE',     r'{species}: coherent\ VM',
         [('Sartre eAu phi', r'$e$Au'), ('Sartre eAu rho', r'$e$Au'), ('Sartre eCa phi', r'$e$Ca')]),
        ('SARTRE',     r'$e$Ag: coherent DDIS', ['Sartre eAg DDIS']),
        ('eSTARlight', r'{species}: coherent\ VM',  [('eSTARlight eCu', r'$e$Cu'), ('eSTARlight eRu', r'$e$Ru')]),
    ]),
    (r'Beyond the Standard Model', [
        ('MadGraph5',  r'ALPs',                  ['MadGraph5']),
    ]),
]

# latest_markers.json keys deliberately left out of the table, with the reason.
OMITTED = {
    'DJANGOH CC': 'charged current; table shows NC only',
    'PYTHIA 6.428 (legacy)': 'superseded by pythia6-eic',
    'PYTHIA 8 charm': 'HFsim charm; table shows inclusive PYTHIA 8',
    'EpIC DDVCS': 'table shows DVCS only',
    'EpIC DVMP': 'table shows DVCS only',
    'DEMPgen K+Lambda': 'kaon row uses eicMesonSFGen',
    'Sartre eAu jpsi': 'unversioned legacy files mixing coherent and incoherent',
}

FOOTNOTE = r"""\textbf{Detector regions} (ePIC pre-TDR).
\textbf{FB}, $\eta<-3.5$: low-$Q^2$ taggers, luminosity monitor (scattered electron only).
\textbf{Bwd}, backward endcap, $-3.5<\eta<-1.5$: Si/MPGD disks, pfRICH, TOF, PbWO$_4$ EMCal, nHCal.
\textbf{Bar}, barrel, $|\eta|<1.5$: Si vertex/tracker, MPGDs, hpDIRC, TOF, imaging EMCal (BIC), HCal.
\textbf{Fwd}, forward endcap, $1.5<\eta<3.5$: tracking disks, dRICH, TOF, W/SciFi EMCal, LFHCAL.
\textbf{B0}, $\eta\approx4.6$--5.9 (5.5--20\,mrad from the hadron beam): B0 tracker and calorimeter; protons, $\Lambda$, light nuclei.
\textbf{FF}, $\eta\gtrsim6$ ($<$5\,mrad from the hadron beam): Roman pots and off-momentum detectors (protons, light nuclei); zero-degree calorimeter (neutrons, $\Lambda$)."""
