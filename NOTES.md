# Notes: decisions, results, open items

The README covers how to run things. This file records why the table is the way
it is. Everything here is either produced by the sweep or encoded in
`sweep/markers.py` / `table/spec.py`.

## Origin

- **Merged from** `/gpfs02/eic/rahmans/mc_gen_sweep/` (sweep and table code) on 2026-11-10.
  - The assessment write-up in `epic-prod-dev/Monte Carlo Generator assessment/` (docs, LaTeX
    summaries, a 28-file pilot study, an unpinned full-tree sweep) is **not** included,
    because this stack doesn't reproduce it.
  - Both originals are unchanged on disk.
- **The sweep used to read** "every `.hepmc3.tree.root` under EVGEN" (xrootd listing plus
  `simulation_campaign_datasets@99a906b`, which has no campaign tags).
  - It now reads only the EVGEN files a campaign consumed (`pins/<campaign>/`).
  - The PCS status-grids page needs a login; the catalog JSON behind it is public, so the catalog is what gets pinned.
- **Files are read** from `/jlab-osdf-ro/eic/EPIC/cache/EVGEN` on dtn2304 (the Rucio PFN base for EIC-XRD).
- **Container:** `eic_xl:26.10-stable`. `run.sh` refuses to run if the tag points to a
  different image digest.

## Table decisions (from the user, encoded in markers.py / spec.py)

- **Files:** only `.hepmc3.tree.root`; TCSGen and beam backgrounds are excluded.
- **Latest sample only:** the highest generator version within each generator + target + process, among the samples the campaign ran.
- **Ions:** Ag and the other ions are shown individually.
- **Layout:** the table fits in one column and is readable for non-experts.
- **Heavy-ion group names** (the user's wording): "nuclear fragments", "no fragments, no
  residual nucleus", "no fragments, residual nucleus".
- **Footnote:** ends at the detector descriptions.
- **Sartre J/ψ is omitted:** only legacy, unversioned files exist, and they mix coherent and incoherent events.
- **Multi-ion row labels** are filled from the species the campaign actually has (`{species}` in `spec.py`).
- **Rows with no campaign data** are dropped and listed in the provenance file.

## 26.07 results (2026-11-10)

- **Lock:** 334 non-gun RECO/FULL output datasets → 204 EVGEN datasets, 11,524 files, 0 unresolved.
  77 of those datasets have no Rucio dataset and are pinned by size and mtime from xrootd.
- **Sweep:** 430 files (3 per dataset), 830k events, 0 errors.
  47 chunks ran on HTCondor (cluster 320703); the 7 still idle ran on eicsub01 with the same `run.sh`.
- **Memory:** 1 GB per job is enough. Peak RSS was 541 MB (all-background chunk c0000).
- **Rows 26.07 has no sample for:** DJANGOH NC (QED radiation), BeAGLE eCa/ePb incoherent VM,
  BeAGLE eCu/eRu DIS, eSTARlight eCu/eRu, MadGraph5 ALPs.
- **Sartre:** coherent VM is eAu only. eAg is coherent DDIS (`sartre2.20-1.0`, 9×115), which gets
  its own row: ● in Bwd/Bar/Fwd, nothing in B0/FF (the nucleus stays in the beam).
- **PYTHIA 8 FF** is blank (median 0.09 particles per event over 29 datasets, just under the 0.1 cut).

## Open items

- [ ] 26.07 has radiative DJANGOH **CC** (4.6.10-4.0) but no NC. Decide whether the QED row should use CC.
- [ ] Confirm the wording and placement of the "eAg: coherent DDIS" row.
- [ ] The caption ○ rule is "median ≥ 0.1, or ≥ 0.5 in a quarter of the samples"; confirm the wording.
