import subprocess
import sys
from pathlib import Path

from app.db.store import SQLiteStore
from app.monitoring.metrics import compute_report


def test_diagnose_script_runs_on_populated_db(tmp_path):
    db = tmp_path / "t.db"
    store = SQLiteStore(db)
    store.save_metric(99950.0, 0.001, compute_report([100000, 99950], [-0.0005]))
    root = Path(__file__).resolve().parents[1]
    out = subprocess.run(
        [sys.executable, str(root / "scripts" / "diagnose.py"), "--db", str(db)],
        capture_output=True, text=True, timeout=60,
    )
    assert out.returncode == 0
    assert "DIAGNOSTIC" in out.stdout and "PERSPECTIVE" in out.stdout


def test_diagnose_handles_missing_db(tmp_path):
    root = Path(__file__).resolve().parents[1]
    out = subprocess.run(
        [sys.executable, str(root / "scripts" / "diagnose.py"), "--db", str(tmp_path / "nope.db")],
        capture_output=True, text=True, timeout=60,
    )
    assert out.returncode == 0
    assert "No database" in out.stdout
