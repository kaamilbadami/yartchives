import re

with open("tests/test_triage_workflow_failures.py", "r") as f:
    content = f.read()

# I appended the new test after `if __name__ == "__main__": unittest.main()`, let's move it into the class.
search = """if __name__ == "__main__":
    unittest.main()

    def test_failure_on_existing_issue_does_not_duplicate_sessions(self):
        gh = FakeGh()
        # Mock an existing workflow-failure issue that was already handled but remains open
        # E.g. Jules is still working on it.
        gh.issues = [
            {
                "number": 1,
                "state": "open",
                "body": "<!-- workflow-failure-signature: Quality checks::tests::Python tests -->\\npriority: P1",
                "labels": [{"name": "workflow-failure"}],
            }
        ]
        gh.jobs_by_run["2"] = failed_jobs()

        mod.triage(ctx(run_id="2", conclusion="failure"), gh.json, gh.run)

        # Should still be one issue, and it should get agent-ready/autonomous-backlog
        self.assertEqual(len(gh.issues), 1)
        self.assertEqual(gh.issues[0]["state"], "open")
        labels = {label["name"] for label in gh.issues[0]["labels"]}
        self.assertEqual(labels, {"workflow-failure", "agent-ready", "autonomous-backlog"})
        # Should NOT have created a new issue
        self.assertFalse(any(call[:2] == ("issue", "create") for call in gh.calls))"""

replace = """    def test_failure_on_existing_issue_does_not_duplicate_sessions(self):
        gh = FakeGh()
        # Mock an existing workflow-failure issue that was already handled but remains open
        # E.g. Jules is still working on it.
        gh.issues = [
            {
                "number": 1,
                "state": "open",
                "body": "<!-- workflow-failure-signature: Quality checks::tests::Python tests -->\\npriority: P1",
                "labels": [{"name": "workflow-failure"}],
            }
        ]
        gh.jobs_by_run["2"] = failed_jobs()

        mod.triage(ctx(run_id="2", conclusion="failure"), gh.json, gh.run)

        # Should still be one issue, and it should get agent-ready/autonomous-backlog
        self.assertEqual(len(gh.issues), 1)
        self.assertEqual(gh.issues[0]["state"], "open")
        labels = {label["name"] for label in gh.issues[0]["labels"]}
        self.assertEqual(labels, {"workflow-failure", "agent-ready", "autonomous-backlog"})
        # Should NOT have created a new issue
        self.assertFalse(any(call[:2] == ("issue", "create") for call in gh.calls))

if __name__ == "__main__":
    unittest.main()"""

content = content.replace(search, replace)

with open("tests/test_triage_workflow_failures.py", "w") as f:
    f.write(content)
