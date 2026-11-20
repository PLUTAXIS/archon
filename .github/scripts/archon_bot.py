"""archon-bot: PR Doctor, reviewer balancer and review-queue digest.

Standard library only. Talks to GitHub through the `gh` CLI (GH_TOKEN in CI).
It only reads API data: it never checks out or runs code from a pull request.

Try it locally (needs `gh auth login`), nothing is written with --dry-run:

    $env:REPO = "PLUTAXIS/archon"
    python .github/scripts/archon_bot.py pr --number 55 --dry-run
    python .github/scripts/archon_bot.py digest --dry-run
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import subprocess
import sys
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

try:
    from datetime import UTC
except ImportError:  # Python < 3.11
    UTC = timezone.utc  # noqa: UP017

PR_MARKER = "<!-- archon-bot:pr-doctor -->"
QUEUE_MARKER = "<!-- archon-bot:review-queue -->"
QUEUE_LABEL = "review-queue"
QUEUE_TITLE = "Review queue (auto-updated)"
ASSIGN_ACTIONS = {"opened", "reopened", "ready_for_review"}
CONFIG_PATH = Path(__file__).resolve().parent.parent / "archon-bot.json"
ZWSP = "\u200b"  # stops @mentions in PR titles from pinging people

ICONS = {
    "ok": ":white_check_mark:",
    "info": ":information_source:",
    "warn": ":warning:",
    "block": ":no_entry:",
}

DEFAULT_CONFIG = {
    "reviewers": [],
    "ignore_requested": [],
    "away": [],
    "reviewers_per_pr": 1,
    "skip_authors": ["dependabot[bot]"],
    "areas": {},
    "source_globs": ["archon/*.py"],
    "test_globs": ["tests/*", "*test_*.py", "*.test.*", "*.spec.*"],
    "golden_regex": r"golden.*\.(json|txt|sha256|hash)$|^tests/golden/",
    "golden_label": "golden-update",
    "data_regex": r"^(Dropzone|Archive_Processed|For_Mainak|For_Senpai)/|\.(xlsx|xlsm|xls|mdb|accdb)$",
    "data_allow_globs": ["samples/*", "tests/*", "*.gitkeep"],
    "data_label": "data-approved",
    "large_pr_lines": 500,
    "min_description_chars": 20,
    "stale_review_days": 3,
}

# Patterns checked against lines ADDED to files under .github/workflows/.
WORKFLOW_RISKS = [
    (
        re.compile(r"\bpull_request_target\b"),
        "uses pull_request_target: it must never check out or run PR code",
    ),
    (
        re.compile(r"\|\s*(?:ba)?sh\b"),
        "pipes downloaded or generated text into a shell",
    ),
    (
        re.compile(r"uses:\s*[\w.-]+/[\w./-]+@(?:main|master|latest)\b"),
        "pins an action to a moving branch instead of a version or commit SHA",
    ),
    (
        re.compile(r"permissions:\s*write-all"),
        "grants write-all permissions",
    ),
    (
        re.compile(
            r"\$\{\{\s*github\.(?:event\.(?:pull_request|issue|comment|review)"
            r"\.(?:title|body|head\.ref)|head_ref)"
        ),
        "puts untrusted PR text in an expression: pass it through env:, never run:",
    ),
]


def log(msg: str) -> None:
    print(f"[archon-bot] {msg}", file=sys.stderr)


class GhError(RuntimeError):
    """A `gh api` call failed."""


def gh_api(path, method="GET", payload=None, paginate=False):
    """Call the GitHub REST API through the gh CLI and return parsed JSON."""
    cmd = ["gh", "api", path]
    if method != "GET":
        cmd += ["-X", method]
    if paginate:
        cmd += ["--paginate", "--slurp"]
    stdin = None
    if payload is not None:
        cmd += ["--input", "-"]
        stdin = json.dumps(payload)
    proc = subprocess.run(
        cmd,
        input=stdin,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if proc.returncode != 0:
        raise GhError(f"{method} {path}: {proc.stderr.strip() or proc.stdout.strip()}")
    out = proc.stdout.strip()
    if not out:
        return None
    data = json.loads(out)
    if paginate:
        flat = []
        for page in data:
            flat.extend(page if isinstance(page, list) else [page])
        return flat
    return data


def load_config(path=CONFIG_PATH):
    cfg = dict(DEFAULT_CONFIG)
    p = Path(path)
    if p.exists():
        cfg.update(json.loads(p.read_text(encoding="utf-8")))
    else:
        log(f"no config at {p}, using defaults")
    return cfg


def matches(path, patterns):
    return any(fnmatch.fnmatchcase(path, p) for p in patterns)


def safe_title(title):
    return (title or "").replace("@", "@" + ZWSP).replace("\n", " ")[:80]


# --------------------------------------------------------------- PR Doctor


def audit_workflows(files):
    """Return (workflow_files_touched, [(file, finding), ...])."""
    touched = False
    findings = []
    seen = set()
    for f in files:
        name = f["filename"]
        if not name.startswith(".github/workflows/"):
            continue
        touched = True
        for line in (f.get("patch") or "").splitlines():
            if not line.startswith("+") or line.startswith("+++"):
                continue
            for rx, msg in WORKFLOW_RISKS:
                if rx.search(line[1:]) and (name, msg) not in seen:
                    seen.add((name, msg))
                    findings.append((name, msg))
    return touched, findings


def short_list(names, limit=5):
    shown = ", ".join(f"`{n}`" for n in names[:limit])
    extra = len(names) - limit
    return shown + (f" and {extra} more" if extra > 0 else "")


def analyze(pr, files, cfg):
    """Pure function: PR + changed files -> areas, size and a list of flags."""
    labels = {
        (lb["name"] if isinstance(lb, dict) else lb) for lb in pr.get("labels", [])
    }
    touched = [f["filename"] for f in files]
    present = [f["filename"] for f in files if f.get("status") != "removed"]
    total = pr.get("additions", 0) + pr.get("deletions", 0)
    flags = []

    areas = sorted(
        name
        for name, pats in cfg["areas"].items()
        if any(matches(n, pats) for n in touched)
    )

    body = pr.get("body") or ""
    if len(body.strip()) < cfg["min_description_chars"]:
        flags.append(
            (
                "warn",
                "The description is empty or very short. Say what changed and why.",
            )
        )
    unchecked = len(re.findall(r"^\s*[-*] \[ \]", body, flags=re.MULTILINE))
    if unchecked:
        flags.append(
            (
                "info",
                f"{unchecked} checklist item(s) in the description are still unchecked.",
            )
        )

    src = [
        n
        for n in present
        if matches(n, cfg["source_globs"]) and not matches(n, cfg["test_globs"])
    ]
    tests = [n for n in touched if matches(n, cfg["test_globs"])]
    if src and not tests:
        flags.append(
            ("warn", f"{len(src)} source file(s) changed but no tests were touched.")
        )
    elif src and tests:
        flags.append(("ok", "Tests were updated alongside the source."))

    golden = [
        n for n in touched if re.search(cfg["golden_regex"], n, flags=re.IGNORECASE)
    ]
    if golden:
        if cfg["golden_label"] in labels:
            flags.append(
                (
                    "info",
                    f"Golden files changed, approved via the `{cfg['golden_label']}` label: {short_list(golden)}",
                )
            )
        else:
            flags.append(
                (
                    "block",
                    f"Golden determinism files changed without the `{cfg['golden_label']}` label: {short_list(golden)}",
                )
            )

    data = [
        n
        for n in present
        if re.search(cfg["data_regex"], n, flags=re.IGNORECASE)
        and not matches(n, cfg["data_allow_globs"])
    ]
    if data:
        if cfg["data_label"] in labels:
            flags.append(
                (
                    "info",
                    f"Data files approved via the `{cfg['data_label']}` label: {short_list(data)}",
                )
            )
        else:
            flags.append(
                (
                    "block",
                    f"Possible raw or production data without the `{cfg['data_label']}` label: {short_list(data)}",
                )
            )

    wf_touched, wf_findings = audit_workflows(files)
    for name, msg in wf_findings[:6]:
        flags.append(("warn", f"`{name}` {msg}."))
    if wf_touched and not wf_findings:
        flags.append(
            (
                "info",
                "Workflow files changed: check permissions and any new third-party actions.",
            )
        )

    if total > cfg["large_pr_lines"]:
        flags.append(
            (
                "warn",
                f"Large PR ({total} lines changed). Smaller PRs get faster, better reviews.",
            )
        )

    if pr.get("draft"):
        flags.append(
            (
                "info",
                "Draft: reviewer assignment starts when it is marked ready for review.",
            )
        )

    return {
        "areas": areas,
        "total": total,
        "files": pr.get("changed_files", len(files)),
        "flags": flags,
    }


def render_comment(pr, result, assigned, note):
    lines = [PR_MARKER, "### PR Doctor", ""]
    lines += ["| | |", "|---|---|"]
    lines.append(
        f"| Size | +{pr.get('additions', 0)} / -{pr.get('deletions', 0)} across {result['files']} file(s) |"
    )
    lines.append(f"| Areas | {', '.join(result['areas']) or 'none detected'} |")
    if assigned:
        lines.append(f"| Reviewer requested | {', '.join(assigned)} |")
    elif note:
        lines.append(f"| Reviewers | {note} |")
    lines.append("")
    flags = result["flags"]
    if flags:
        lines.append("**Checks**")
        lines.append("")
        order = {"block": 0, "warn": 1, "info": 2, "ok": 3}
        for level, text in sorted(flags, key=lambda f: order[f[0]]):
            lines.append(f"- {ICONS[level]} {text}")
    else:
        lines.append(f"{ICONS['ok']} Nothing to flag.")
    lines += [
        "",
        "<sub>Advisory summary, updated on every push. Merge-blocking rules live in the Repo guards workflow.</sub>",
    ]
    return "\n".join(lines)


def pick_reviewers(pool, author, load, pr_number, away=()):
    """Rank reviewers: fewest open review requests first, rotating on ties."""
    away_l = {a.lower() for a in away}
    n = max(len(pool), 1)
    ranked = []
    for i, login in enumerate(pool):
        low = login.lower()
        if low == author.lower() or low in away_l:
            continue
        ranked.append((load.get(low, 0), (i + pr_number) % n, login))
    ranked.sort()
    return [login for _, _, login in ranked]


def assign_reviewers(repo, pr, cfg, dry_run=False):
    pool = cfg["reviewers"]
    if not pool:
        return [], ""
    ignore = {x.lower() for x in cfg["ignore_requested"]}
    already = {r["login"].lower() for r in pr.get("requested_reviewers", [])} - ignore
    if already & {p.lower() for p in pool}:
        return [], "A reviewer from the pool is already requested."

    load = {}
    for other in (
        gh_api(f"repos/{repo}/pulls?state=open&per_page=100", paginate=True) or []
    ):
        for r in other.get("requested_reviewers", []):
            key = r["login"].lower()
            load[key] = load.get(key, 0) + 1

    number = pr["number"]
    ranked = pick_reviewers(pool, pr["user"]["login"], load, number, cfg["away"])
    assigned = []
    for login in ranked:
        if len(assigned) >= cfg["reviewers_per_pr"]:
            break
        if dry_run:
            assigned.append(login)
            continue
        try:
            gh_api(
                f"repos/{repo}/pulls/{number}/requested_reviewers",
                method="POST",
                payload={"reviewers": [login]},
            )
            assigned.append(login)
        except GhError as err:
            log(f"could not request {login}: {err}")
    note = (
        ""
        if assigned
        else "No reviewer could be assigned. Check `reviewers` in .github/archon-bot.json."
    )
    return assigned, note


def upsert_comment(repo, number, body):
    comments = (
        gh_api(f"repos/{repo}/issues/{number}/comments?per_page=100", paginate=True)
        or []
    )
    for c in comments:
        is_ours = (
            PR_MARKER in (c.get("body") or "")
            and (c.get("user") or {}).get("type") == "Bot"
        )
        if is_ours:
            gh_api(
                f"repos/{repo}/issues/comments/{c['id']}",
                method="PATCH",
                payload={"body": body},
            )
            return "updated"
    gh_api(
        f"repos/{repo}/issues/{number}/comments", method="POST", payload={"body": body}
    )
    return "created"


def run_pr(repo, number, action, cfg, dry_run=False):
    pr = gh_api(f"repos/{repo}/pulls/{number}")
    author = pr["user"]["login"]
    if author.lower() in {a.lower() for a in cfg["skip_authors"]}:
        log(f"skipping #{number}: author {author} is in skip_authors")
        return None
    files = (
        gh_api(f"repos/{repo}/pulls/{number}/files?per_page=100", paginate=True) or []
    )
    result = analyze(pr, files, cfg)
    assigned, note = [], ""
    if action in ASSIGN_ACTIONS and not pr.get("draft"):
        assigned, note = assign_reviewers(repo, pr, cfg, dry_run=dry_run)
    body = render_comment(pr, result, assigned, note)
    if dry_run:
        print(body)
        return body
    log(f"comment {upsert_comment(repo, number, body)} on #{number}")
    return body


# --------------------------------------------------------------- review queue


def parse_ts(value):
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def review_state(reviews):
    """Latest decisive review per reviewer -> (approved, changes_requested)."""
    latest = {}
    for r in sorted(reviews, key=lambda r: r.get("submitted_at") or ""):
        user = (r.get("user") or {}).get("login")
        state = r.get("state")
        if not user or state in ("COMMENTED", "PENDING"):
            continue
        latest[user] = state
    approved = sorted(u for u, s in latest.items() if s == "APPROVED")
    changes = sorted(u for u, s in latest.items() if s == "CHANGES_REQUESTED")
    return approved, changes


def ci_state(repo, sha):
    try:
        data = gh_api(f"repos/{repo}/commits/{sha}/check-runs?per_page=100") or {}
    except GhError as err:
        log(f"could not read checks for {sha[:7]}: {err}")
        return "unknown"
    runs = data.get("check_runs", [])
    if not runs:
        return "none"
    bad = {"failure", "timed_out", "action_required", "startup_failure"}
    if any(r.get("conclusion") in bad for r in runs):
        return "failing"
    if any(r.get("status") != "completed" for r in runs):
        return "pending"
    return "passing"


def classify_pr(pr, reviews, ci, now, cfg):
    author = pr["user"]["login"]
    approved, changes = review_state(reviews or [])
    idle = (now - parse_ts(pr["updated_at"])).days
    if pr.get("draft"):
        bucket = "draft"
    elif author.lower() in {a.lower() for a in cfg["skip_authors"]}:
        bucket = "bot"
    elif ci == "failing":
        bucket = "ci_failing"
    elif changes:
        bucket = "changes_requested"
    elif approved:
        bucket = "ready"
    else:
        bucket = "needs_review"
    return {
        "number": pr["number"],
        "title": safe_title(pr.get("title")),
        "author": author,
        "bucket": bucket,
        "approved": approved,
        "changes": changes,
        "requested": sorted(r["login"] for r in pr.get("requested_reviewers", [])),
        "ci": ci,
        "age": (now - parse_ts(pr["created_at"])).days,
        "idle": idle,
        "overdue": bucket == "needs_review" and idle >= cfg["stale_review_days"],
    }


def fmt_row(r):
    parts = [f"- #{r['number']} {r['title']} (by {r['author']})"]
    if r["bucket"] == "ready":
        parts.append(f"approved by {', '.join(r['approved'])}")
        if r["ci"] == "pending":
            parts.append("CI still running")
    elif r["bucket"] == "needs_review":
        parts.append("waiting on " + (", ".join(r["requested"]) or "nobody assigned"))
        parts.append(f"idle {r['idle']}d" + (" **overdue**" if r["overdue"] else ""))
    elif r["bucket"] == "changes_requested":
        parts.append(f"changes requested by {', '.join(r['changes'])}")
    elif r["bucket"] == "ci_failing":
        parts.append("CI failing")
    return " - ".join(parts)


SECTIONS = [
    ("ready", "Ready to merge"),
    ("needs_review", "Waiting for review"),
    ("changes_requested", "Changes requested"),
    ("ci_failing", "CI failing"),
]


def render_digest(rows, now):
    counts = Counter(r["bucket"] for r in rows)
    lines = [
        QUEUE_MARKER,
        "# Review queue",
        f"_Updated {now:%Y-%m-%d %H:%M} UTC by archon-bot. This issue is rewritten on every run, do not edit it._",
        "",
        (
            f"**{len(rows)} open PRs:** {counts['ready']} ready, "
            f"{counts['needs_review']} need review, "
            f"{counts['changes_requested']} changes requested, "
            f"{counts['ci_failing']} CI failing, "
            f"{counts['draft']} draft, {counts['bot']} from bots."
        ),
    ]
    for bucket, title in SECTIONS:
        group = sorted(
            (r for r in rows if r["bucket"] == bucket), key=lambda r: -r["idle"]
        )
        if group:
            lines += ["", f"## {title}", ""] + [fmt_row(r) for r in group]
    return "\n".join(lines)


def webhook_text(rows, issue_url):
    counts = Counter(r["bucket"] for r in rows)
    overdue = sorted((r for r in rows if r["overdue"]), key=lambda r: -r["idle"])
    text = (
        f"Archon review queue: {counts['ready']} ready to merge, {counts['needs_review']} need review "
        f"({len(overdue)} overdue), {counts['changes_requested']} with changes requested, "
        f"{counts['ci_failing']} failing CI."
    )
    if overdue:
        text += (
            " Longest waiting: "
            + ", ".join(f"#{r['number']} ({r['idle']}d)" for r in overdue[:5])
            + "."
        )
    if issue_url:
        text += f" {issue_url}"
    return text


def post_webhook(url, text):
    if not url.startswith("https://"):
        log("webhook ignored: URL must start with https://")
        return
    key = "content" if "discord" in url else "text"
    req = urllib.request.Request(
        url,
        data=json.dumps({key: text[:1900]}).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": "archon-bot"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            log(f"webhook responded {resp.status}")
    except Exception as err:  # noqa: BLE001
        log(f"webhook failed: {err}")


def upsert_queue_issue(repo, body):
    found = (
        gh_api(f"repos/{repo}/issues?labels={QUEUE_LABEL}&state=open&per_page=30") or []
    )
    existing = next((i for i in found if "pull_request" not in i), None)
    if existing:
        out = gh_api(
            f"repos/{repo}/issues/{existing['number']}",
            method="PATCH",
            payload={"body": body},
        )
    else:
        out = gh_api(
            f"repos/{repo}/issues",
            method="POST",
            payload={"title": QUEUE_TITLE, "body": body, "labels": [QUEUE_LABEL]},
        )
    return (out or {}).get("html_url")


def run_digest(repo, cfg, dry_run=False, webhook_url=None, now=None):
    now = now or datetime.now(UTC)
    skip = {a.lower() for a in cfg["skip_authors"]}
    rows = []
    for pr in (
        gh_api(f"repos/{repo}/pulls?state=open&per_page=100", paginate=True) or []
    ):
        reviews = ci = None
        if not pr.get("draft") and pr["user"]["login"].lower() not in skip:
            reviews = gh_api(
                f"repos/{repo}/pulls/{pr['number']}/reviews?per_page=100", paginate=True
            )
            ci = ci_state(repo, pr["head"]["sha"])
        rows.append(classify_pr(pr, reviews, ci, now, cfg))
    body = render_digest(rows, now)
    if dry_run:
        print(body)
        print("\n--- webhook text ---")
        print(webhook_text(rows, None))
        return rows
    issue_url = upsert_queue_issue(repo, body)
    log(f"review queue updated: {issue_url}")
    if webhook_url:
        post_webhook(webhook_url, webhook_text(rows, issue_url))
    return rows


# --------------------------------------------------------------- CLI


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(prog="archon_bot")
    parser.add_argument("--config", default=str(CONFIG_PATH))
    sub = parser.add_subparsers(dest="cmd", required=True)

    def add_common(p):
        p.add_argument(
            "--repo",
            default=os.environ.get("REPO") or os.environ.get("GITHUB_REPOSITORY"),
        )
        p.add_argument(
            "--dry-run", action="store_true", help="print instead of writing to GitHub"
        )

    p_pr = sub.add_parser("pr", help="analyze one pull request")
    add_common(p_pr)
    p_pr.add_argument(
        "--number", type=int, default=int(os.environ.get("PR_NUMBER") or 0) or None
    )
    p_pr.add_argument("--action", default=os.environ.get("EVENT_ACTION") or "opened")
    p_dg = sub.add_parser("digest", help="update the review-queue issue")
    add_common(p_dg)

    args = parser.parse_args(argv)
    if not args.repo:
        parser.error("repo not set: use --repo or the REPO environment variable")
    cfg = load_config(args.config)
    try:
        if args.cmd == "pr":
            if not args.number:
                parser.error("pr needs --number (or PR_NUMBER)")
            run_pr(args.repo, args.number, args.action, cfg, dry_run=args.dry_run)
        else:
            run_digest(
                args.repo,
                cfg,
                dry_run=args.dry_run,
                webhook_url=os.environ.get("DIGEST_WEBHOOK_URL"),
            )
    except GhError as err:
        log(f"GitHub API error: {err}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
