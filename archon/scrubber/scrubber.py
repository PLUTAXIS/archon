#!/usr/bin/env python3
"""Plutaxis scrubber: masks the confidential data in an Excel file on YOUR computer.

WHAT IT CHANGES
  * Text in cells, comments and file properties -> dummy text (Text_1, Text_2 ...)
  * Numbers typed into cells                    -> random digits, same shape
  * Saved results of formulas                   -> removed (Excel recalculates them)
  * Text and cached values inside charts        -> removed or replaced
WHAT IT KEEPS (on purpose, we need the skeleton)
  * Formulas, sheet names, sheet layout, and VBA macro code

SAFETY: standard library only. Reads one file, writes one NEW file, never
changes your original, and never opens a network connection.

USAGE:  python scrubber.py MyFile.xlsm      (creates MyFile.scrubbed.xlsm)
OPTION: --keep-headers  leave row-1 text (column names) readable; everything else is masked.
"""
import argparse
import os
import random
import re
import secrets
import sys
import zipfile

# Parts we cannot safely scrub. If one is present we tell the user to check it.
REVIEW = {
    "vbaProject.bin": "VBA macro code (kept on purpose): check it for names, passwords or amounts",
    "pivotCache": "pivot tables keep a copy of the source data",
    "externalLinks": "links to other files (may show file paths and values)",
    "customXml": "custom data added by other programs",
    "embeddings": "embedded files",
    "xl/tables/": "table column names (formulas need them)",
    "docProps/custom": "custom file properties",
}
# File properties that often hold real names.
PROPERTY_TAGS = ("dc:creator", "cp:lastModifiedBy", "dc:title", "dc:subject",
                 "dc:description", "cp:keywords", "Company", "Manager")
# One cell, either <c .../> (empty) or <c ...>...</c>.
CELL = re.compile(r"<c\b([^>]*?)(?:/>|>(.*?)</c>)", re.DOTALL)


class ScrubError(Exception):
    """A problem we can explain to the user in plain words."""


class Masker:
    """Creates dummy values. The same original always gets the same dummy."""

    def __init__(self):
        self.rng = random.Random(secrets.token_bytes(16))  # new random seed every run
        self.texts, self.numbers = {}, {}
        self.keep_headers, self.keep = False, set()  # keep = shared strings used in row 1
        self.count = dict.fromkeys(
            ("strings", "numbers", "formula_results", "comments", "properties", "charts"), 0)

    def text(self, original):
        self.count["strings"] += 1
        if original not in self.texts:
            self.texts[original] = "Text_%d" % (len(self.texts) + 1)
        return self.texts[original]

    def number(self, original):
        """145000.5 -> e.g. 830217.2 (same digits, same decimals, same exponent)."""
        self.count["numbers"] += 1
        if original not in self.numbers:
            mantissa, exponent = re.match(r"([^eE]*)(.*)", original).groups()
            if not any(c in "123456789" for c in mantissa):
                self.numbers[original] = original  # zero (or not a number): reveals nothing
            else:
                out, first = [], True
                for ch in mantissa:
                    if ch.isdigit():
                        lowest = 1 if (first and ch != "0") else 0  # keep the size of the number
                        out.append(str(self.rng.randint(lowest, 9)))
                        first = False
                    else:
                        out.append(ch)
                self.numbers[original] = "".join(out) + exponent
        return self.numbers[original]


def row_of(attrs):
    found = re.search(r'\br="[A-Z]+(\d+)"', attrs)
    return int(found.group(1)) if found else 10 ** 9  # unknown row counts as data

def header_strings(zin):
    """Numbers of the shared strings used in row 1 of any sheet (they stay readable)."""
    keep = set()
    for name in zin.namelist():
        if pick_handler(name) is scrub_sheet:
            for cell in CELL.finditer(zin.read(name).decode("utf-8")):
                attrs, body = cell.group(1), cell.group(2) or ""
                value = re.search(r"<v>(\d+)</v>", body)
                if value and row_of(attrs) == 1 and re.search(r'\bt="s"', attrs):
                    keep.add(int(value.group(1)))
    return keep

def scrub_sheet(xml, m):
    """Redact cell values in a worksheet XML part, keeping formulas and structure."""
    def fix_cell(match):
        attrs, body = match.group(1), match.group(2)
        if body is None:  # empty cell
            return match.group(0)
        if re.search(r"<f[\s>/]", body):  # formula cell: keep <f>, drop its saved result
            body, n = re.subn(r"<v>.*?</v>|<v/>", "", body, flags=re.DOTALL)
            m.count["formula_results"] += n
        else:
            kind = re.search(r'\bt="(\w+)"', attrs)
            kind = kind.group(1) if kind else "n"
            if kind == "n":  # a typed-in number
                body = re.sub(r"<v>(.*?)</v>", lambda x: "<v>%s</v>" % m.number(x.group(1)),
                              body, flags=re.DOTALL)
            elif kind == "inlineStr":  # text stored inside the cell
                if not (m.keep_headers and row_of(attrs) == 1):
                    body = re.sub(r"<is>.*?</is>",
                                  lambda x: "<is><t>%s</t></is>" % m.text(x.group(0)), body, flags=re.DOTALL)
            elif kind == "s" and m.keep:  # a header word reused further down: mask it here
                value = re.search(r"<v>(\d+)</v>", body)
                if value and int(value.group(1)) in m.keep and row_of(attrs) != 1:
                    attrs = attrs.replace('t="s"', 't="inlineStr"')
                    body = "<is><t>%s</t></is>" % m.text(("shared", int(value.group(1))))
            # other "s" cells point into sharedStrings (scrubbed separately); "b"/"e" are TRUE/FALSE/errors
        return "<c%s>%s</c>" % (attrs, body)
    return CELL.sub(fix_cell, xml)

def scrub_shared_strings(xml, m):
    idx = [0]  # position of each string in the table

    def fix(x):
        i, idx[0] = idx[0], idx[0] + 1
        if i in m.keep or x.group(0) == "<si/>":
            return x.group(0)  # a header word we were asked to keep, or an empty string
        return "<si><t>%s</t></si>" % m.text(x.group(0))
    return re.sub(r"<si>.*?</si>|<si/>", fix, xml, flags=re.DOTALL)

def scrub_properties(xml, m):
    """Redact author and metadata tags in a document properties XML part."""
    for tag in PROPERTY_TAGS:
        xml, n = re.subn(r"(<%s\b[^>]*>).*?(</%s>)" % (tag, tag), r"\1redacted\2", xml, flags=re.DOTALL)
        m.count["properties"] += n
    return xml

def scrub_comments(xml, m):
    xml = re.sub(r"<author>.*?</author>", "<author>redacted</author>", xml, flags=re.DOTALL)
    xml, n = re.subn(r"<t\b[^>/]*>.*?</t>", "<t>redacted</t>", xml, flags=re.DOTALL)
    m.count["comments"] += n
    return xml

def scrub_threaded_comments(xml, m):
    xml, n = re.subn(r"<text>.*?</text>", "<text>redacted</text>", xml, flags=re.DOTALL)
    m.count["comments"] += n
    return re.sub(r'\b(displayName|userId|providerId)="[^"]*"', r'\1="redacted"', xml)

def scrub_chart(xml, m):
    """Strip cached chart data and redact titles and labels in a chart XML part."""
    xml, n1 = re.subn(r"<c:(numCache|strCache)>.*?</c:\1>", "", xml, flags=re.DOTALL)  # saved data copies
    xml, n2 = re.subn(r"<a:t>.*?</a:t>", "<a:t>redacted</a:t>", xml, flags=re.DOTALL)  # titles, labels
    m.count["charts"] += n1 + n2
    return xml

def pick_handler(name):
    """Which scrubbing function (if any) applies to this part of the file."""
    if name.startswith("xl/worksheets/") and name.endswith(".xml"):
        return scrub_sheet
    if name == "xl/sharedStrings.xml":
        return scrub_shared_strings
    if name in ("docProps/core.xml", "docProps/app.xml"):
        return scrub_properties
    if re.fullmatch(r"xl/comments(?:/comment)?\d*\.xml", name):
        return scrub_comments
    if name.startswith(("xl/threadedComments/", "xl/persons/")):
        return scrub_threaded_comments
    if re.fullmatch(r"xl/charts/chart\d*\.xml", name):
        return scrub_chart
    return None  # copied byte-for-byte (this is how VBA stays intact)

def scrub_file(src, dst, keep_headers=False):
    """Write a scrubbed copy of src to dst. Returns (counts, things_to_review)."""
    m, untouched = Masker(), []
    m.keep_headers = keep_headers
    with zipfile.ZipFile(src) as zin:
        if "xl/workbook.xml" not in zin.namelist():
            raise ScrubError("This does not look like a normal .xlsx/.xlsm workbook "
                             "(.xlsb is not supported).")
        if keep_headers:
            m.keep = header_strings(zin)
        with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                data = zin.read(item)
                handler = pick_handler(item.filename)
                if handler:
                    data = handler(data.decode("utf-8"), m).encode("utf-8")
                else:
                    untouched.append(item.filename)
                info = zipfile.ZipInfo(item.filename, item.date_time)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = item.external_attr
                zout.writestr(info, data)
    review = [why for key, why in REVIEW.items() if any(key in n for n in untouched)]
    return m.count, review


def fail(message):
    print("ERROR: " + message, file=sys.stderr)
    return 1


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Mask confidential data in an Excel file (.xlsx / .xlsm) on this computer.")
    parser.add_argument("file", help="the Excel file to scrub")
    parser.add_argument("-o", "--output", help="where to save the result (default: NAME.scrubbed.ext)")
    parser.add_argument("--keep-headers", action="store_true", help="leave row-1 text readable (column names)")
    args = parser.parse_args(argv)

    stem, ext = os.path.splitext(args.file)
    dst = args.output or stem + ".scrubbed" + ext
    if not os.path.isfile(args.file):
        return fail("file not found: " + args.file)
    if os.path.abspath(dst) == os.path.abspath(args.file):
        return fail("the output must be a different file; your original is never changed.")
    if not zipfile.is_zipfile(args.file):
        return fail("this is not a modern Excel file. It may be password-protected, or an old "
                    ".xls/.xlsb file. Remove the password or 'Save As' .xlsx/.xlsm and try again.")
    try:
        counts, review = scrub_file(args.file, dst, args.keep_headers)
    except (ScrubError, zipfile.BadZipFile, UnicodeDecodeError) as err:
        if os.path.exists(dst):
            os.remove(dst)
        return fail(str(err) or "the file could not be read.")

    print("Done. Saved: " + dst)
    print("  text values masked:        %d" % counts["strings"])
    print("  typed numbers masked:      %d" % counts["numbers"])
    print("  formula results removed:   %d" % counts["formula_results"])
    print("  comments/properties/charts cleaned: %d" % (
        counts["comments"] + counts["properties"] + counts["charts"]))
    print("Kept as-is on purpose: formulas, sheet names, layout, VBA code.")
    if args.keep_headers:
        print("Row 1 text was KEPT readable (--keep-headers). Check it holds no real names.")
    if review:
        print("PLEASE CHECK before sending (copied unchanged, may contain real data):")
        for why in review:
            print("  - " + why)
    return 0


if __name__ == "__main__":
    sys.exit(main())