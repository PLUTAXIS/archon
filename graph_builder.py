"""graph_builder.py - build dag_graph.json from formulas + decompiled VBA text.

Usage:  python graph_builder.py samples\\sample_input.json -o dag_graph.json
Input format: see GRAPH_BUILDER.md. Stdlib + networkx only. No network.
"""
import argparse
import json
import re
import sys
from collections import Counter

import networkx as nx

MAX_RANGE_CELLS = 2000   # bigger ranges become one "range" node
MAX_COL = 16384          # XFD
EDGE_LABELS = ("formula", "vba_write")

STRING_RE = re.compile(r'"(?:[^"]|"")*"')
CELL_RE = re.compile(r"^\$?([A-Za-z]{1,3})\$?(\d+)$")
REF_RE = re.compile(
    r"""(?<![\w.$'!])
        (?:(?:'((?:[^']|'')+)'|([A-Za-z_][\w.]*))!)?
        \$?([A-Za-z]{1,3})\$?(\d+)
        (?::\$?([A-Za-z]{1,3})\$?(\d+))?
        (?![\w(!])""",
    re.X,
)
PROC_RE = re.compile(
    r"^\s*(?:(?:Public|Private|Friend)\s+)?(?:Static\s+)?(?:Sub|Function)\s+(\w+)", re.I)
IF_THEN_RE = re.compile(r"^\s*If\b.*?\bThen\s+(.+)$", re.I)
SKIP_RE = re.compile(
    r"^\s*(If|ElseIf|While|Do|Loop|Case|Dim|Const|For|Debug|Select|With|Set|Call|Option|Rem)\b",
    re.I)
STATIC_LHS_RE = re.compile(
    r'^(?:ThisWorkbook\.)?'
    r'(?:(?:Worksheets|Sheets)\s*\(\s*"([^"]+)"\s*\)\s*\.)?'
    r'(?:ActiveSheet\.)?'
    r'(Range|Cells)\s*\(([^()]*)\)\s*(?:\.(?:Value2?|Formula\w*))?\s*$',
    re.I,
)
RANGE_ARG_RE = re.compile(
    r'^"\s*(\$?[A-Za-z]{1,3}\$?\d+(?::\$?[A-Za-z]{1,3}\$?\d+)?)\s*"$')
CELLS_ARG_RE = re.compile(r'^\s*(\d+)\s*,\s*(\d+|"[A-Za-z]{1,3}")\s*$')


def col_to_num(col):
    n = 0
    for ch in col.upper():
        n = n * 26 + ord(ch) - 64
    return n


def num_to_col(n):
    s = ""
    while n > 0:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def split_cell(cell):
    m = CELL_RE.match(cell.strip())
    if not m or int(m.group(2)) < 1 or col_to_num(m.group(1)) > MAX_COL:
        raise ValueError("bad cell address: %r" % cell)
    return col_to_num(m.group(1)), int(m.group(2))


def norm_cell(cell):
    c, r = split_cell(cell)
    return "%s%d" % (num_to_col(c), r)


def extract_refs(formula, home_sheet):
    """Return [(sheet, 'A1', 'B2' or None)] for every reference in a formula."""
    text = STRING_RE.sub('""', formula)
    out = []
    for m in REF_RE.finditer(text):
        qsheet, usheet, c1, r1, c2, r2 = m.groups()
        if int(r1) < 1 or col_to_num(c1) > MAX_COL:
            continue
        if c2 and (int(r2) < 1 or col_to_num(c2) > MAX_COL):
            continue
        sheet = qsheet.replace("''", "'") if qsheet else (usheet or home_sheet)
        a = "%s%d" % (c1.upper(), int(r1))
        b = "%s%d" % (c2.upper(), int(r2)) if c2 else None
        out.append((sheet, a, b))
    return out


def _value_node(g, sheet, cell):
    nid = "%s!%s" % (sheet, cell)
    if nid not in g:
        g.add_node(nid, type="value", sheet=sheet, cell=cell)
    return nid


def _range_ids(g, sheet, a, b):
    """Node ids for a cell or range; huge ranges collapse to one 'range' node."""
    if b is None:
        return [_value_node(g, sheet, a)]
    (c1, r1), (c2, r2) = split_cell(a), split_cell(b)
    clo, chi, rlo, rhi = min(c1, c2), max(c1, c2), min(r1, r2), max(r1, r2)
    if (chi - clo + 1) * (rhi - rlo + 1) > MAX_RANGE_CELLS:
        text = "%s%d:%s%d" % (num_to_col(clo), rlo, num_to_col(chi), rhi)
        rid = "%s!%s" % (sheet, text)
        if rid not in g:
            g.add_node(rid, type="range", sheet=sheet, cell=text)
        return [rid]
    return [_value_node(g, sheet, "%s%d" % (num_to_col(c), r))
            for r in range(rlo, rhi + 1) for c in range(clo, chi + 1)]


def _need(item, idx, where, keys):
    if not isinstance(item, dict):
        raise ValueError("%s[%d] must be an object" % (where, idx))
    for k in keys:
        if not isinstance(item.get(k), str) or not item[k].strip():
            raise ValueError("%s[%d] is missing text field %r" % (where, idx, k))
    return [item[k] for k in keys]


def _strip_comment(line):
    in_str = False
    for i, ch in enumerate(line):
        if ch == '"':
            in_str = not in_str
        elif ch == "'" and not in_str:
            return line[:i]
    return line


def _lhs_of_assignment(code):
    """Text before the first top-level single '=' (outside strings/parens), else None."""
    in_str, depth = False, 0
    for i, ch in enumerate(code):
        if ch == '"':
            in_str = not in_str
        elif in_str:
            continue
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == "=" and depth == 0:
            prev = code[i - 1] if i else ""
            nxt = code[i + 1] if i + 1 < len(code) else ""
            if prev in "<>!:" or nxt == "=":
                continue
            return code[:i]
    return None


def _is_write(lhs):
    if re.search(r"\b(Range|Cells)\s*\(", lhs, re.I):
        return True
    if re.search(r"\.(Value2?|Formula\w*)\s*$", lhs.strip(), re.I):
        return True
    return lhs.strip().startswith("[")


def _resolve_static(lhs, default_sheet):
    """Return (sheet, a, b) if the write target is fully static, else (None, reason)."""
    m = STATIC_LHS_RE.match(lhs.strip())
    if not m:
        return None, "target is not a plain Range/Cells call (variable, With, Offset, etc.)"
    sheet = m.group(1) or default_sheet
    if not sheet:
        return None, "sheet not known (ActiveSheet / no sheet given)"
    kind, args = m.group(2).lower(), m.group(3)
    if kind == "range":
        am = RANGE_ARG_RE.match(args.strip())
        if not am:
            return None, "address built at runtime"
        parts = am.group(1).replace("$", "").split(":")
        try:
            a = norm_cell(parts[0])
            b = norm_cell(parts[1]) if len(parts) > 1 else None
        except ValueError:
            return None, "address not valid"
        return (sheet, a, b), None
    cm = CELLS_ARG_RE.match(args)
    if not cm:
        return None, "row/column built at runtime"
    row, col = int(cm.group(1)), cm.group(2)
    col_n = int(col) if col.isdigit() else col_to_num(col.strip('"'))
    if row < 1 or col_n < 1 or col_n > MAX_COL:
        return None, "row/column out of range"
    return (sheet, "%s%d" % (num_to_col(col_n), row), None), None


def _add_vba(g, mod, idx):
    module, code = _need(mod, idx, "vba", ("module", "code"))
    default_sheet = mod.get("default_sheet") or None
    proc = "(module)"
    for lineno, raw in enumerate(code.splitlines(), start=1):
        line = _strip_comment(raw).strip()
        if not line:
            continue
        pm = PROC_RE.match(line)
        if pm:
            proc = pm.group(1)
            continue
        im = IF_THEN_RE.match(line)
        if im:
            line = im.group(1).strip()
        if SKIP_RE.match(line):
            continue
        lhs = _lhs_of_assignment(line)
        if lhs is None or not _is_write(lhs):
            continue
        pid = "VBA:%s.%s" % (module, proc)
        if pid not in g:
            g.add_node(pid, type="vba_proc", module=module, procedure=proc)
        target, reason = _resolve_static(lhs, default_sheet)
        if target is None:
            uid = "VBA_UNKNOWN:%s:L%d" % (module, lineno)
            g.add_node(uid, type="vba_write_range_unknown", module=module,
                       procedure=proc, line=lineno, text=line[:200],
                       reason=reason, flagged=True)
            g.add_edge(pid, uid, label="vba_write")
            continue
        sheet, a, b = target
        for nid in _range_ids(g, sheet, a, b):
            g.nodes[nid]["vba_written"] = True
            g.add_edge(pid, nid, label="vba_write")


def build_graph(data):
    if not isinstance(data, dict):
        raise ValueError("input must be a JSON object")
    g = nx.DiGraph()
    formulas = data.get("formulas", [])
    if not isinstance(formulas, list) or not isinstance(data.get("vba", []), list):
        raise ValueError("'formulas' and 'vba' must be lists")
    parsed = []
    for i, f in enumerate(formulas):
        sheet, cell, formula = _need(f, i, "formulas", ("sheet", "cell", "formula"))
        cell = norm_cell(cell)
        nid = "%s!%s" % (sheet, cell)
        attrs = dict(type="formula", sheet=sheet, cell=cell, formula=formula)
        if isinstance(f.get("cluster"), str) and f["cluster"]:
            attrs["cluster"] = f["cluster"]
        g.add_node(nid, **attrs)
        parsed.append((nid, sheet, formula))
    for nid, sheet, formula in parsed:
        for rs, a, b in extract_refs(formula, sheet):
            for src in _range_ids(g, rs, a, b):
                g.add_edge(src, nid, label="formula")
    for i, mod in enumerate(data.get("vba", [])):
        _add_vba(g, mod, i)
    return g


def validate(g):
    """Return a list of problems (empty list = valid)."""
    errors = []
    orphans = sorted(n for n in g.nodes if g.degree(n) == 0)
    if orphans:
        errors.append("orphan nodes (no edges): %s" % ", ".join(orphans[:10]))
    bad = [(u, v) for u, v, d in g.edges(data=True) if d.get("label") not in EDGE_LABELS]
    if bad:
        errors.append("unlabelled/unknown-label edges: %s" % bad[:10])
    labels = {d.get("label") for _, _, d in g.edges(data=True)}
    if "formula" not in labels:
        errors.append("graph has no 'formula' edges (not built from formulas)")
    if "vba_write" not in labels:
        errors.append("graph has no 'vba_write' edges (not built from VBA writes)")
    return errors


def to_dict(g):
    nodes = [dict(id=n, **d) for n, d in sorted(g.nodes(data=True))]
    edges = [dict(source=u, target=v, label=d["label"])
             for u, v, d in sorted(g.edges(data=True))]
    unknown = [dict(node=n["id"], module=n["module"], procedure=n["procedure"],
                    line=n["line"], text=n["text"], reason=n["reason"])
               for n in nodes if n["type"] == "vba_write_range_unknown"]
    return {
        "meta": {
            "nodes": len(nodes),
            "edges": len(edges),
            "nodes_by_type": dict(Counter(n["type"] for n in nodes)),
            "edges_by_label": dict(Counter(e["label"] for e in edges)),
            "vba_unknown_writes": len(unknown),
            "has_cycles": not nx.is_directed_acyclic_graph(g),
        },
        "nodes": nodes,
        "edges": edges,
        "vba_unknown_writes": unknown,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="Build dag_graph.json")
    ap.add_argument("input", help="input JSON (formulas + vba)")
    ap.add_argument("-o", "--output", default="dag_graph.json")
    args = ap.parse_args(argv)
    try:
        with open(args.input, encoding="utf-8") as fh:
            data = json.load(fh)
        g = build_graph(data)
    except (OSError, ValueError) as exc:
        print("ERROR: %s" % exc)
        return 1
    errors = validate(g)
    if errors:
        print("VALIDATION FAILED - nothing written:")
        for e in errors:
            print("  - " + e)
        return 1
    out = to_dict(g)
    with open(args.output, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2)
    m = out["meta"]
    print("OK: %d nodes, %d edges, %d unknown VBA writes, cycles=%s -> %s" % (
        m["nodes"], m["edges"], m["vba_unknown_writes"], m["has_cycles"], args.output))
    return 0


if __name__ == "__main__":
    sys.exit(main())