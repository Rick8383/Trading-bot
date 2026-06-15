from app.learning.improvement_engine import propose_improvements
from app.learning.knowledge_base import KnowledgeBase
from app.learning.postmortem import post_mortem, setup_signature, signature_for_record
from app.learning.trade_journal import TradeJournal, TradeRecord


def _loss(regime="bear", action="LONG", conviction=70, rr=2.5, flags=None, ret=-0.03):
    return TradeRecord(
        symbol="X", action=action, entry=100, exit=97, stop_loss=96, take_profit=110,
        quantity=10, pnl=ret * 1000, return_pct=ret, reason="stop_loss",
        conviction=conviction, reward_risk=rr, regime=regime, risk_flags=flags or [],
    )


def _win(**kw):
    kw.setdefault("ret", 0.05)
    r = _loss(**kw)
    r.pnl = abs(r.pnl)
    r.return_pct = abs(r.return_pct)
    r.exit = 110
    r.reason = "take_profit"
    return r


def test_signature_symmetry():
    rec = _loss(regime="bear", action="LONG")
    sig_pre = setup_signature(action="LONG", regime="bear", conviction=70, reward_risk=2.5, risk_flags=[])
    assert "regime_misalignment:bear" in signature_for_record(rec)
    assert "regime_misalignment:bear" in sig_pre


def test_postmortem_tags_a_loss():
    tags = post_mortem(_loss(regime="bear", action="LONG", conviction=50, flags=["rsi_extreme"]))
    keys = {t.key for t in tags}
    assert "regime_misalignment:bear" in keys
    assert "low_conviction_loss" in keys
    assert "risk_flag_loss:rsi_extreme" in keys
    # Winners produce no error tags.
    assert post_mortem(_win()) == []


def test_knowledge_base_learns_and_penalizes(tmp_path):
    kb = KnowledgeBase(tmp_path / "kb.json", min_samples=8)
    # Feed a clearly losing context many times.
    for _ in range(10):
        rec = _loss(regime="bear", action="LONG")
        kb.ingest(rec, post_mortem(rec))
    sig = setup_signature(action="LONG", regime="bear", conviction=70, reward_risk=2.5, risk_flags=[])
    penalties = kb.penalties(sig)
    assert penalties.get("regime_misalignment:bear", 0) > 0
    assert any(l.key == "regime_misalignment:bear" for l in kb.active_lessons())


def test_knowledge_base_does_not_penalize_winning_context(tmp_path):
    kb = KnowledgeBase(tmp_path / "kb.json", min_samples=8)
    for _ in range(10):
        rec = _win(regime="bull", action="LONG", conviction=50)  # low_conviction but winning
        kb.ingest(rec, post_mortem(rec))
    sig = setup_signature(action="LONG", regime="bull", conviction=50, reward_risk=2.5, risk_flags=[])
    assert kb.penalties(sig) == {}  # positive expectancy -> no penalty


def test_knowledge_base_persists(tmp_path):
    path = tmp_path / "kb.json"
    kb = KnowledgeBase(path, min_samples=8)
    for _ in range(9):
        rec = _loss(flags=["mtf_trend_conflict"])
        kb.ingest(rec, post_mortem(rec))
    kb.save()
    reloaded = KnowledgeBase(path, min_samples=8)
    assert "flag:mtf_trend_conflict" in reloaded.lessons


def test_journal_roundtrip(tmp_path):
    j = TradeJournal(tmp_path / "journal.jsonl")
    rec = _loss()
    rec.error_tags = ["regime_misalignment:bear"]
    j.append(rec)
    loaded = j.load()
    assert len(loaded) == 1 and loaded[0].symbol == "X"
    assert loaded[0].error_tags == ["regime_misalignment:bear"]


def test_improvement_engine_proposes(tmp_path):
    kb = KnowledgeBase(tmp_path / "kb.json", min_samples=8)
    journal = []
    for _ in range(12):
        rec = _loss(regime="bear", action="LONG")
        kb.ingest(rec, post_mortem(rec))
        journal.append(rec)
    proposals = propose_improvements(kb, journal)
    assert proposals
    assert any("regime" in p.title.lower() for p in proposals)
