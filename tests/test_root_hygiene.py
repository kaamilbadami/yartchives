from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class RootHygieneTests(unittest.TestCase):
    def test_scratch_diagnostics_do_not_live_at_repository_root(self):
        forbidden_exact = {
            "test_script.py",
            "follow_up_report.md",
        }
        forbidden_prefixes = (
            "debug_",
            "measure_churn",
        )

        offenders = sorted(
            path.name
            for path in ROOT.iterdir()
            if path.is_file()
            and (
                path.name in forbidden_exact
                or path.name.startswith(forbidden_prefixes)
            )
        )

        self.assertEqual(
            offenders,
            [],
            "Move temporary diagnostics/reports under tests/, scripts/, or audit/ instead of the repository root.",
        )


if __name__ == "__main__":
    unittest.main()
