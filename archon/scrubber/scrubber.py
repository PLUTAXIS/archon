#!/usr/bin/env python3
"""Plutaxis scrubber: masks the confidential data in an Excel file on YOUR computer.
CHANGES: cell/comment/property text -> dummy text; typed numbers -> random digits, same shape;
saved formula results -> removed; chart text/caches -> removed or replaced; quoted text inside
formulas and dropdown lists -> the same dummy as the cell text; print headers/footers -> redacted;
pivot-table and external-link copies of data -> masked; external file paths -> redacted;
pictures -> a blank 1x1 image.
KEEPS (on purpose): formula structure, sheet names, layout, VBA macro code.
SAFETY: standard library only. Reads one file, writes one NEW file, never changes the original,
never opens a network connection.
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

REVIEW = {
    "vbaProject.bin": "VBA macro code (kept on purpose): check it for names, passwords or amounts",
    "pivotCache": "pivot tables keep a copy of the source data",
    "externalLinks": "links to other files (may show file paths and values)",
    "customXml": "custom data added by other programs",
    "embeddings": "embedded files",
    "docProps/custom": "custom file properties",
}
PROPERTY_TAGS = ("dc:creator", "cp:lastModifiedBy", "dc:title", "dc:subject",
                 "dc:description", "cp:keywords", "Company", "Manager")
CELL = re.compile(r"<c\b([^>]*?)(?:/>|>(.*?)</c>)", re.DOTALL)
# Plain text out of <t>...</t> or rich runs <r><t>...</t></r><r>...</r>.
INNER_TEXT_RUNS = re.compile(r"<t[^>]*>(.*?)</t>", re.DOTALL)

def inner_text(fragment):
    """The plain text carried by one <is>...</is> or <si>...</si> body
    (single <t> or several rich <r><t> runs concatenated)."""
    return "".join(INNER_TEXT_RUNS.findall(fragment))

QUOTED = re.compile(r'"((?:[^"]|"")+)"')  # a non-empty "text" literal inside a formula
BLANK_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000b494441"
    "54789c6360000200000500017a5eab3f0000000049454e44ae426082")


def mask_quoted(formula, m):
    """'IF(B2="Acme",1,0)' -> 'IF(B2="Text_3",1,0)': the dummy matches the cell text's."""
    return QUOTED.sub(lambda x: '"%s"' % m.text(x.group(1)), formula)


class ScrubError(Exception):
    """A problem we can explain to the user in plain words."""

class Masker:
    """Creates dummy values. The same original always gets the same dummy."""

    def __init__(self):
        self.rng = random.Random(secrets.token_bytes(16))  # new random seed every run
        self.texts, self.numbers = {}, {}
        self.keep_headers, self.keep = False, set()  # keep = shared strings used in row 1
        self.count = dict.fromkeys(
            ("strings", "numbers", "formula_results", "comments", "properties", "charts",
             "pictures", "copies"), 0)

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
            body = re.sub(r"(<f\b[^>]*>)(.*?)(</f>)",
                          lambda x: x.group(1) + mask_quoted(x.group(2), m) + x.group(3),
                          body, flags=re.DOTALL)
        else:
            kind = re.search(r"""\bt=(?:"(\w+)"|'(\w+)')""", attrs)
            kind = (kind.group(1) or kind.group(2)) if kind else "n"
            if kind == "n":  # a typed-in number
                body = re.sub(r"<v>(.*?)</v>", lambda x: "<v>%s</v>" % m.number(x.group(1)),
                              body, flags=re.DOTALL)
            elif kind == "inlineStr":  # text stored inside the cell
                if not (m.keep_headers and row_of(attrs) == 1):
                    body = re.sub(r"<is>(.*?)</is>",
                                  lambda x: "<is><t>%s</t></is>" % m.text(inner_text(x.group(1))),
                                  body, flags=re.DOTALL)
            elif kind == "s" and m.keep:  # a header word reused further down: mask it here
                value = re.search(r"<v>(\d+)</v>", body)
                if value and int(value.group(1)) in m.keep and row_of(attrs) != 1:
                    attrs = re.sub(r"""t=(?:"s"|'s')""", 't="inlineStr"', attrs)
                    body = "<is><t>%s</t></is>" % m.text(("shared", int(value.group(1))))
            # other "s" cells point into sharedStrings (scrubbed separately); "b"/"e" are TRUE/FALSE/errors
        return "<c%s>%s</c>" % (attrs, body)
    xml = CELL.sub(fix_cell, xml)
    # dropdown lists and conditional-format rules can quote real names too
    xml = re.sub(r"(<formula\d?>)(.*?)(</formula\d?>)",
                 lambda x: x.group(1) + mask_quoted(x.group(2), m) + x.group(3), xml, flags=re.DOTALL)
    return re.sub(r"(<(odd|even|first)(Header|Footer)>).*?(</\2\3>)", r"\1&amp;Credacted\4",
                  xml, flags=re.DOTALL)  # print headers/footers

def scrub_shared_strings(xml, m):
    idx = [0]  # position of each string in the table

    def fix(x):
        i, idx[0] = idx[0], idx[0] + 1
        if i in m.keep or x.group(0) == "<si/>":
            return x.group(0)  # a header word we were asked to keep, or an empty string
        return "<si><t>%s</t></si>" % m.text(inner_text(x.group(1) or ""))
    return re.sub(r"<si>(.*?)</si>|<si/>", fix, xml, flags=re.DOTALL)

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

def scrub_table(xml, m):
    # Column names must match the header row's dummy, or Excel repairs the file on open.
    if m.keep_headers:
        return xml
    return re.sub(r'(<tableColumn\b[^>]*\bname=")([^"]*)(")',
                  lambda x: x.group(1) + m.text(x.group(2)) + x.group(3), xml)

def scrub_threaded_comments(xml, m):
    xml, n = re.subn(r"<text>.*?</text>", "<text>redacted</text>", xml, flags=re.DOTALL)
    m.count["comments"] += n
    return re.sub(r'\b(displayName|userId|providerId)="[^"]*"', r'\1="redacted"', xml)

def scrub_chart(xml, m):
    """Charts and drawings: strip cached chart data; redact titles, labels, text boxes and
    picture descriptions (often the original file name)."""
    xml, n1 = re.subn(r"<c:(numCache|strCache)>.*?</c:\1>", "", xml, flags=re.DOTALL)  # saved data copies
    xml, n2 = re.subn(r"<a:t>.*?</a:t>", "<a:t>redacted</a:t>", xml, flags=re.DOTALL)  # titles, labels
    m.count["charts"] += n1 + n2
    return re.sub(r'\s(descr|title)="[^"]*"', "", xml)

def scrub_workbook(xml, m):
    """Excel stores the folder the file was last saved in (user and client names)."""
    return re.sub(r'(<x15ac:absPath\b[^>]*\burl=")[^"]*(")', r"\1\2", xml)

def scrub_pivot_cache(xml, m):
    """Pivot tables keep their own copy of the source data: mask it like the cells."""
    m.count["copies"] += 1
    xml = re.sub(r'(<s v=")([^"]*)(")', lambda x: x.group(1) + m.text(x.group(2)) + x.group(3), xml)
    xml = re.sub(r'(<n v=")([^"]*)(")', lambda x: x.group(1) + m.number(x.group(2)) + x.group(3), xml)
    xml = re.sub(r'(<cacheField\b[^>]*\bname=")([^"]*)(")',
                 lambda x: x.group(0) if m.keep_headers else x.group(1) + m.text(x.group(2)) + x.group(3), xml)
    xml = re.sub(r'\brefreshedBy="[^"]*"', 'refreshedBy="redacted"', xml)  # who refreshed it
    return re.sub(r'\s(minValue|maxValue)="[^"]*"', "", xml)  # optional summaries of real numbers

def scrub_external_link(xml, m):
    """A link to another workbook keeps copies of the values it reads: mask them."""
    m.count["copies"] += 1
    def fix(x):
        attrs, value = x.group(1), x.group(2)
        masked = m.text(value) if re.search(r'\bt="(?:str|s)"', attrs) else m.number(value)
        return "<cell%s><v>%s</v>" % (attrs, masked)
    return re.sub(r"<cell\b([^>]*)><v>(.*?)</v>", fix, xml, flags=re.DOTALL)

def scrub_link_target(xml, m):
    """External file paths name people, clients and folders: keep only that a link exists.
    Every target here points at the other file (Excel also stores a relative fallback)."""
    def fix(x):
        m.count["copies"] += 1
        return 'Target="redacted_link%d%s"' % (m.count["copies"], os.path.splitext(x.group(1))[1][:5])
    return re.sub(r'Target="([^"]*)"', fix, xml)

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
    if re.fullmatch(r"xl/(?:charts/chart|drawings/drawing)\d*\.xml", name):
        return scrub_chart
    if name == "xl/workbook.xml":
        return scrub_workbook
    if re.fullmatch(r"xl/tables/table\d*\.xml", name):
        return scrub_table
    if re.fullmatch(r"xl/pivotCache/pivotCache(?:Records|Definition)\d*\.xml", name):
        return scrub_pivot_cache
    if re.fullmatch(r"xl/externalLinks/externalLink\d*\.xml", name):
        return scrub_external_link
    if re.fullmatch(r"xl/externalLinks/_rels/externalLink\d*\.xml\.rels", name):
        return scrub_link_target
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
                if re.fullmatch(r"xl/media/[^/]+\.(?:png|jpe?g|gif|bmp)", item.filename, re.IGNORECASE):
                    data = BLANK_PNG  # a picture can show anything: replace it with a blank one
                    m.count["pictures"] += 1
                elif handler:
                    data = handler(data.decode("utf-8"), m).encode("utf-8")
                else:
                    untouched.append(item.filename)
                info = zipfile.ZipInfo(item.filename, item.date_time)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = item.external_attr
                zout.writestr(info, data)
    review = ["%s: %s" % (name, next((why for key, why in REVIEW.items() if key in name), "uninspected workbook component copied unchanged; check for confidential data")) for name in untouched]
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
    print("  pictures blanked: %d   pivot/external-link copies masked: %d" % (
        counts["pictures"], counts["copies"]))
    print("Kept as-is on purpose: formula structure, sheet names, layout, VBA code.")
    if args.keep_headers:
        print("Row 1 text was KEPT readable (--keep-headers). Check it holds no real names.")
    print("SANITIZATION STATUS: " + ("REVIEW_REQUIRED" if review else "PROCESSING_COMPLETE (not a safety certification)"))
    if review:
        print("PLEASE CHECK before sending (copied unchanged, may contain real data):")
        for why in review:
            print("  - " + why)
    return 0
if __name__ == "__main__":
    sys.exit(main())
