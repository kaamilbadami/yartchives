import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "measure_fortune_500_coverage.py"
spec = importlib.util.spec_from_file_location("measure_fortune_500_coverage", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

def test_measure_fortune_500_coverage_script_runs():
    """Ensure the F500 coverage script runs without errors on the real data."""
    script_path = ROOT / "scripts" / "measure_fortune_500_coverage.py"
    result = subprocess.run(
        [sys.executable, str(script_path)],
        capture_output=True,
        text=True
    )
    assert result.returncode == 0, f"Script failed with error: {result.stderr}"
    assert "Fortune 500 Internship Coverage Report" in result.stdout
    assert "Benchmark Population: 500 employers" in result.stdout
    assert "Miss Classification" in result.stdout


def test_mixed_provider_hints_are_not_mislabeled_unsupported():
    assert mod.classify_unresolved_provider_families({"custom_unknown", "workday"}) == "unresolved_host"
    assert mod.classify_unresolved_provider_families({"unknown", "greenhouse"}) == "unresolved_host"
    assert mod.classify_unresolved_provider_families({"custom_unknown", "unknown"}) == "unsupported_ats"
    assert mod.classify_unresolved_provider_families(set()) == "no_domain_hint"
