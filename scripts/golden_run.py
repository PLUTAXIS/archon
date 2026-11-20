"""End-to-end golden run: scrub -> verify -> report."""
import sys
import zipfile

sys.path.insert(0, ".")  # ensure repo-root archon/ is importable

from archon.scrubber.scrubber import scrub_file
from archon.scrubber.verify_scrub import verify, formulas

SRC = "golden_input.xlsx"
DST = "golden_scrubbed.xlsx"
WORDS = ("Acme Corp Confidential",)

# 1. Scrub
scrub_file(SRC, DST)
print(f"[1/3] scrub complete -> {DST}")

# 2. Verify: formulas intact AND confidential words gone
result = verify(SRC, DST, words=WORDS)
if result is False:
    sys.exit("[2/3] verify FAILED - do not proceed")
print("[2/3] verify passed: formulas intact, confidential strings gone")

# 3. Report: what formulas survived the scrub?
with zipfile.ZipFile(DST) as z:
    fs = formulas(z)
print(f"[3/3] formulas found in scrubbed file: {len(fs)}")
for f in fs:
    print("      ", f)

print("GOLDEN RUN: PASS")
