import importlib.util
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "triage_source_quarantines.py"
SPEC = importlib.util.spec_from_file_location("triage_source_quarantines", SCRIPT)
mod = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(mod)


def feed(sources):
    return {"sources": sources, "jobs": []}


def quarantined(name, error, **extra):
    return {
        "status": "quarantined",
        "name": name,
        "error": error,
        **extra,
    }


class FakeGh:
    def __init__(self):
        self.issues = []
        self.calls = []

    def open_issues(self):
        return [issue.copy() for issue in self.issues if issue["state"] == "open"]

    def run(self, *args):
        self.calls.append(args)
        if args[:2] == ("label", "create"):
            return
        if args[:2] == ("issue", "create"):
            labels = [
                args[index + 1]
                for index, value in enumerate(args)
                if value == "--label"
            ]
            self.issues.append(
                {
                    "number": len(self.issues) + 1,
                    "state": "open",
                    "title": args[args.index("--title") + 1],
                    "body": args[args.index("--body") + 1],
                    "labels": [{"name": label} for label in labels],
                }
            )
            return
        if args[:2] == ("issue", "edit"):
            issue = self._issue(int(args[2]))
            if "--body" in args:
                issue["body"] = args[args.index("--body") + 1]
            labels = {label["name"] for label in issue["labels"]}
            index = 5
            while index < len(args):
                if args[index] == "--add-label":
                    labels.add(args[index + 1])
                    index += 2
                elif args[index] == "--remove-label":
                    labels.discard(args[index + 1])
                    index += 2
                else:
                    index += 1
            issue["labels"] = [{"name": label} for label in sorted(labels)]
            return
        if args[:2] == ("issue", "comment"):
            return
        if args[:2] == ("issue", "close"):
            self._issue(int(args[2]))["state"] = "closed"
            return
        raise AssertionError(f"unexpected gh call: {args}")

    def _issue(self, number):
        return next(issue for issue in self.issues if issue["number"] == number)


class SourceQuarantineTriageTests(unittest.TestCase):
    def test_first_quarantine_does_not_create_issue(self):
        gh = FakeGh()
        previous = feed({"icims:acme": {"status": "healthy", "name": "Acme"}})
        current = feed(
            {
                "icims:acme": quarantined(
                    "Acme",
                    "StructuralSourceError: expected job cards, got landing page",
                )
            }
        )

        groups = mod.triage(
            "kaamilbadami/yartchives",
            previous,
            current,
            load_open_issues=gh.open_issues,
            run_gh=gh.run,
        )

        self.assertEqual(groups, {})
        self.assertEqual(gh.issues, [])

    def test_two_consecutive_quarantines_create_autonomous_jules_issue(self):
        gh = FakeGh()
        source = quarantined(
            "Acme",
            "StructuralSourceError: expected job cards, got landing page",
            auto_discovered=True,
        )

        mod.triage(
            "kaamilbadami/yartchives",
            feed({"icims:acme": source}),
            feed({"icims:acme": source}),
            load_open_issues=gh.open_issues,
            run_gh=gh.run,
        )

        self.assertEqual(len(gh.issues), 1)
        issue = gh.issues[0]
        labels = {label["name"] for label in issue["labels"]}
        self.assertEqual(
            labels,
            {"source-quarantine", "agent-ready", "autonomous-backlog"},
        )
        self.assertIn("<!-- autonomous-task -->", issue["body"])
        self.assertIn("area: coverage", issue["body"])
        self.assertIn("resources: coverage, source-collection", issue["body"])
        self.assertIn("icims:acme", issue["body"])

    def test_same_family_and_root_cause_group_into_one_issue(self):
        gh = FakeGh()
        first = quarantined(
            "Acme",
            "StructuralSourceError: expected 12 cards at https://acme.example/jobs",
        )
        second = quarantined(
            "Beta",
            "StructuralSourceError: expected 8 cards at https://beta.example/jobs",
        )
        sources = {"icims:acme": first, "icims:beta": second}

        groups = mod.triage(
            "kaamilbadami/yartchives",
            feed(sources),
            feed(sources),
            load_open_issues=gh.open_issues,
            run_gh=gh.run,
        )

        self.assertEqual(len(groups), 1)
        self.assertEqual(len(gh.issues), 1)
        self.assertIn("Affected sources: **2**", gh.issues[0]["body"])

    def test_configured_false_without_explicit_quarantine_is_not_escalated(self):
        gh = FakeGh()
        disabled = {"configured": False, "name": "Intentional disable"}

        mod.triage(
            "kaamilbadami/yartchives",
            feed({"workday:disabled": disabled}),
            feed({"workday:disabled": disabled}),
            load_open_issues=gh.open_issues,
            run_gh=gh.run,
        )

        self.assertEqual(gh.issues, [])

    def test_recovery_closes_existing_issue(self):
        gh = FakeGh()
        source = quarantined(
            "Acme",
            "StructuralSourceError: expected job cards, got landing page",
        )
        previous = feed({"icims:acme": source})
        current = feed({"icims:acme": source})

        mod.triage(
            "kaamilbadami/yartchives",
            previous,
            current,
            load_open_issues=gh.open_issues,
            run_gh=gh.run,
        )
        self.assertEqual(gh.issues[0]["state"], "open")

        mod.triage(
            "kaamilbadami/yartchives",
            current,
            feed({"icims:acme": {"status": "healthy", "name": "Acme"}}),
            load_open_issues=gh.open_issues,
            run_gh=gh.run,
        )

        self.assertEqual(gh.issues[0]["state"], "closed")
        labels = {label["name"] for label in gh.issues[0]["labels"]}
        self.assertNotIn("agent-ready", labels)
        self.assertNotIn("autonomous-backlog", labels)

    def test_existing_signature_is_updated_not_duplicated(self):
        gh = FakeGh()
        source = quarantined(
            "Acme",
            "StructuralSourceError: expected job cards, got landing page",
        )
        feeds = (feed({"icims:acme": source}), feed({"icims:acme": source}))

        mod.triage(
            "kaamilbadami/yartchives",
            *feeds,
            load_open_issues=gh.open_issues,
            run_gh=gh.run,
        )
        mod.triage(
            "kaamilbadami/yartchives",
            *feeds,
            load_open_issues=gh.open_issues,
            run_gh=gh.run,
        )

        self.assertEqual(len(gh.issues), 1)
        creates = [call for call in gh.calls if call[:2] == ("issue", "create")]
        self.assertEqual(len(creates), 1)


if __name__ == "__main__":
    unittest.main()
