from app.api.app import app
from app.monitoring.metrics import compute_report
from app.monitoring.report import generate_html_report, svg_area, write_report


def test_svg_area_renders():
    svg = svg_area([1, 2, 3, 2, 5])
    assert svg.startswith("<svg") and "polyline" in svg
    assert svg_area([]).startswith("<svg")  # empty is safe


def test_generate_html_report_is_self_contained(tmp_path):
    report = compute_report([100_000, 101_000, 100_500, 103_000], [0.01, -0.005, 0.025])
    out = write_report(
        tmp_path / "r.html", title="Test", report=report,
        equity_curve=[100_000, 101_000, 100_500, 103_000], trades=[], lessons=[],
        proposals=[], initial_capital=100_000,
    )
    htmltext = out.read_text()
    # No external resources: fully offline-capable.
    assert "http://" not in htmltext and "https://" not in htmltext.replace("lang=", "")
    assert "<svg" in htmltext
    assert "Sharpe" in htmltext


def test_api_endpoints_work_without_db():
    from fastapi.testclient import TestClient
    client = TestClient(app)
    assert client.get("/health").json()["status"] == "ok"
    # Store-backed endpoints degrade gracefully to empty when no DB exists.
    assert "trades" in client.get("/trades").json()
    assert "lessons" in client.get("/lessons").json()
    assert client.get("/dashboard").status_code == 200


def test_kill_switch_endpoints():
    from fastapi.testclient import TestClient
    client = TestClient(app)
    assert client.get("/kill-switch").json()["active"] is False
    client.post("/kill-switch/trigger", params={"reason": "test"})
    assert client.get("/kill-switch").json()["active"] is True
    client.post("/kill-switch/reset")
    assert client.get("/kill-switch").json()["active"] is False
