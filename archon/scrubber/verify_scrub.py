"""verify_scrub.py - check a scrubbed workbook against its original (offline, stdlib only).

Usage:  python verify_scrub.py ORIGINAL.xlsm SCRUBBED.xlsm [word ...]

Checks: same parts, VBA identical byte for byte, same formulas, and none of the
words you list remain in raw ZIP part bytes. This is NOT full VBA decompilation:
compressed or encoded strings may not be detected.
Prints OK / FAIL / SKIP per check. Exit code 0 only when nothing failed.
"""
import hashlib
import re
import sys
import zipfile

SHEET = re.compile(r"xl/worksheets/sheet\d+\.xml")
FORMULA = re.compile(r"<f\b[^>]*?(?:/>|>.*?</f>)", re.DOTALL)


def formulas(z):
    found = []
    for name in sorted(z.namelist()):
        if SHEET.fullmatch(name):
            found += FORMULA.findall(z.read(name).decode("utf-8-sig"))
    return found


def verify(original, scrubbed, words=()):
    """Return a list of (status, message). Status is OK, FAIL or SKIP."""
    results = []
    with zipfile.ZipFile(original) as a, zipfile.ZipFile(scrubbed) as b:
        for label, archive in (("original", a), ("scrubbed", b)):
            names = archive.namelist()
            duplicates = sorted({n for n in names if names.count(n) > 1})
            results.append(("FAIL" if duplicates else "OK",
                            "%s ZIP has no duplicate entries%s" %
                            (label, ": " + ", ".join(duplicates) if duplicates else "")))
            corrupt = archive.testzip()
            results.append(("FAIL" if corrupt else "OK",
                            "%s ZIP CRC integrity%s" %
                            (label, ": " + corrupt if corrupt else " verified")))

        same = a.namelist() == b.namelist()
        results.append(("OK" if same else "FAIL", "same file parts in the same order"))
        macros = [n for n in a.namelist() if n.endswith("vbaProject.bin")]
        if not macros:
            results.append(("SKIP", "no VBA in this file, so macros were NOT tested"))
        for n in macros:
            ok = n in b.namelist() and hashlib.sha256(a.read(n)).digest() == hashlib.sha256(b.read(n)).digest()
            results.append(("OK" if ok else "FAIL", "VBA identical byte for byte (%s)" % n))
        if macros:
            results.append(("SKIP", "VBA compressed/encoded strings were not decompiled; raw-byte scan only"))
        fa, fb = formulas(a), formulas(b)
        results.append(("OK" if fa == fb else "FAIL", "all %d formulas unchanged" % len(fa)))
        for word in words:
            needles = [word.lower().encode("utf-8"),
                       word.lower().encode("utf-16le"),
                       word.lower().encode("utf-16be")]
            hits = []
            for n in b.namelist():
                raw = b.read(n).lower()
                if any(needle and needle in raw for needle in needles):
                    hits.append(n)
            results.append(("FAIL" if hits else "OK",
                            "'%s' %s (UTF-8/UTF-16 raw-byte scan)" %
                            (word, "FOUND in " + ", ".join(hits) if hits else "not found")))
    return results


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    if len(args) < 2:
        print(__doc__)
        return 2
    results = verify(args[0], args[1], args[2:])
    for status, message in results:
        print("%-5s %s" % (status, message))
    return 1 if any(s == "FAIL" for s, _ in results) else 0


if __name__ == "__main__":
    sys.exit(main())
