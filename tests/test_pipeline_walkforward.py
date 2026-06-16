from app.backtesting.pipeline_walkforward import run_pipeline_walk_forward
from app.core.config import load_config


def test_pipeline_walk_forward_runs_out_of_sample():
    settings = load_config()
    wf = run_pipeline_walk_forward(
        settings, symbols=["A", "B"], bars=300, train=100, test=60, warmup=100,
    )
    assert len(wf.windows) >= 1
    for w in wf.windows:
        # No look-ahead: the test window strictly follows the train window.
        assert w.test[0] == w.train[1]
        assert w.test[0] >= 120                 # indicator lead-in respected
    assert wf.oos_report.n_trades == len(wf.oos_trade_returns)


def test_pipeline_walk_forward_param_selection():
    settings = load_config()
    wf = run_pipeline_walk_forward(
        settings, symbols=["A"], bars=280, train=100, test=60, warmup=100,
        param_name="min_rr", grid=[2.0, 3.0],
    )
    assert wf.param_name == "min_rr"
    for w in wf.windows:
        assert w.param in (2.0, 3.0)            # a grid value was selected in-sample
