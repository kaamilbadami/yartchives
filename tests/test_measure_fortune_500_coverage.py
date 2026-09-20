import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

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
