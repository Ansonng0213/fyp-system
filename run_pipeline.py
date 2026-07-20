"""Run all pipeline stages in order from the repo root. Stops on first error."""
import subprocess, sys, pathlib, time

ROOT = pathlib.Path(__file__).parent
STAGES = sorted((ROOT / "pipeline").glob("[0-9][0-9]_*.py"))

for s in STAGES:
    print(f"\n{'#'*70}\n# RUNNING {s.name}\n{'#'*70}")
    t = time.time()
    r = subprocess.run([sys.executable, str(s)], cwd=ROOT)
    if r.returncode != 0:
        print(f"\nFAILED at {s.name} — fix and re-run.")
        sys.exit(1)
    print(f"# {s.name} done in {time.time()-t:.0f}s")
print("\nAll stages complete.")
