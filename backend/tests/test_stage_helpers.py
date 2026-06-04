from datetime import date

from src.db.models import Session, SessionStage, SessionStatus
from src.services.stage import append_activity_event, set_status, transition_stage


def _session() -> Session:
    return Session(
        market_profile="oil",
        timeframe_start=date(2024, 1, 1),
        timeframe_end=date(2024, 6, 30),
    )


def test_transition_stage_updates_stage():
    s = _session()
    transition_stage(s, SessionStage.FEATURIZING)
    assert s.stage == "featurizing"


def test_transition_stage_appends_history():
    s = _session()
    transition_stage(s, SessionStage.FEATURIZING)
    transition_stage(s, SessionStage.ANALYZING)
    assert len(s.stage_history) == 2
    assert s.stage_history[0]["stage"] == "featurizing"
    assert s.stage_history[1]["stage"] == "analyzing"
    assert "entered_at" in s.stage_history[0]


def test_set_status_updates_status():
    s = _session()
    set_status(s, SessionStatus.RUNNING)
    assert s.status == "running"


def test_set_status_sets_error():
    s = _session()
    set_status(s, SessionStatus.FAILED, error="something went wrong")
    assert s.error == "something went wrong"


def test_append_activity_event_adds_metadata():
    s = _session()
    append_activity_event(
        s, {"type": "stage_transition", "from": "configuring", "to": "featurizing"}
    )
    assert len(s.activity_events) == 1
    ev = s.activity_events[0]
    assert "event_id" in ev
    assert "created_at" in ev
    assert ev["type"] == "stage_transition"
