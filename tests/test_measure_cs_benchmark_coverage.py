import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_measure_cs_benchmark_coverage_script_runs():
    """Ensure the benchmark coverage script runs without errors on the real data."""
    script_path = ROOT / "scripts" / "measure_cs_benchmark_coverage.py"
    result = subprocess.run(
        [sys.executable, str(script_path)],
        capture_output=True,
        text=True
    )
    assert result.returncode == 0, f"Script failed with error: {result.stderr}"
    assert "High-Value CS Employer Benchmark Coverage Report" in result.stdout
    assert "Benchmark Population: 30 employers" in result.stdout
    assert "Miss Classification" in result.stdout
