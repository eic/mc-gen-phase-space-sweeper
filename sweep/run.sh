#!/bin/bash
# Usage: run.sh <campaign> <chunk> <repo>. Maps the chunk's EVGEN files onto ePIC regions inside eic_xl.
set -u
CAMPAIGN=$1; CHUNK=$2; REPO=$3; RUN=$REPO/run/$CAMPAIGN
IMG=/cvmfs/singularity.opensciencegrid.org/eicweb/eic_xl:26.10-stable
IMG_DIGEST=sha256:a2/eca318d51ed70f6cc64dba6bb032762ad937c4624c1cf056bb3f7a3beb627d   # what the tag resolved to for the 2026-10-25 and 26.07 sweeps
case "$(readlink -f "$IMG")" in
  */$IMG_DIGEST) ;;
  *) echo "eic_xl:26.10-stable moved to $(readlink -f "$IMG"); update IMG_DIGEST deliberately" >&2; exit 3 ;;
esac
cd "${_CONDOR_SCRATCH_DIR:-/tmp}"
singularity exec -B /gpfs02 "$IMG" python3 "$REPO/sweep/phase_space.py" "$RUN/in/$CHUNK.txt" > "$CHUNK.json" 2> "$CHUNK.err"
rc=$?
mkdir -p "$RUN/out" "$RUN/log"
cp "$CHUNK.json" "$RUN/out/$CHUNK.json"; cp "$CHUNK.err" "$RUN/log/$CHUNK.pyerr"
exit $rc
