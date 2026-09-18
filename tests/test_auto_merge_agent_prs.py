import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "auto_merge_agent_prs.py"
SPEC = importlib.util.spec_from_file_location("auto_merge_agent_prs", MODULE_PATH)
mod = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(mod)


def pr(*, body="Closes #10", files=(), head_sha="abc", draft=False, repo="kaamilbadami/yartchives"):
    return {
        "number": 20,
        "state": "open",
        "draft": draft,
        "body": body,
        "head": {"sha": head_sha, "repo": {"full_name": repo}},
        "base": {"ref": "main"},
        "_files": list(files),
    }


def issue(*, labels=("autonomous-backlog", "jules-review-ready"), state="open"):
    return {
        "number": 10,
        "state": state,
        "labels": [{"name": label} for label in labels],
    }


def runs(sha="abc", conclusion="success"):
    return [
        {
            "name": "Quality checks",
            "head_sha": sha,
            "status": "completed",
            "conclusion": conclusion,
        }
    ]


class AutoMergeAgentPrTests(unittest.TestCase):
    def test_accepts_green_terminal_autonomous_agent_pr(self):
        candidate = pr(files=("app.js", "tests/apply-next-ui.test.cjs"))
        ok, reason = mod.eligible_pr(
            candidate,
            repo="kaamilbadami/yartchives",
            issue=issue(),
            changed_paths=candidate["_files"],
            quality_runs=runs(),
        )
        self.assertTrue(ok)
        self.assertEqual(reason, "eligible")

    def test_requires_exact_head_quality_success(self):
        candidate = pr()
        ok, _ = mod.eligible_pr(
            candidate,
            repo="kaamilbadami/yartchives",
            issue=issue(),
            changed_paths=["app.js"],
            quality_runs=runs(sha="older"),
        )
        self.assertFalse(ok)

    def test_blocks_control_plane_and_benchmark_changes(self):
        for path in (
            ".github/workflows/quality.yml",
            "scripts/dispatch_autonomous_issues.py",
            "scripts/triage_workflow_failures.py",
            "scripts/auto_merge_agent_prs.py",
            "requirements.txt",
            "audit/samples/northeast-midatlantic-cs-2026-09-17.json",
        ):
            with self.subTest(path=path):
                self.assertEqual(mod.blocked_changed_paths([path]), [path])

    def test_requires_terminal_agent_label_and_rejects_product_decisions(self):
        candidate = pr()
        for labels in (
            ("autonomous-backlog",),
            ("autonomous-backlog", "jules-review-ready", "needs-product-decision"),
            ("jules-review-ready",),
        ):
            with self.subTest(labels=labels):
                ok, _ = mod.eligible_pr(
                    candidate,
                    repo="kaamilbadami/yartchives",
                    issue=issue(labels=labels),
                    changed_paths=["app.js"],
                    quality_runs=runs(),
                )
                self.assertFalse(ok)

    def test_rejects_forks_drafts_and_unlinked_prs(self):
        cases = (
            pr(repo="someone/fork"),
            pr(draft=True),
            pr(body="Related to #10"),
        )
        for candidate in cases:
            with self.subTest(candidate=candidate):
                ok, _ = mod.eligible_pr(
                    candidate,
                    repo="kaamilbadami/yartchives",
                    issue=issue(),
                    changed_paths=["app.js"],
                    quality_runs=runs(),
                )
                self.assertFalse(ok)

    def test_codex_review_ready_is_also_terminal(self):
        self.assertTrue(
            mod.autonomous_issue_ready(
                issue(labels=("autonomous-backlog", "codex-review-ready"))
            )
        )


if __name__ == "__main__":
    unittest.main()
