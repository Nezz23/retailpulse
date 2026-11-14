import pytest
from streamlit.testing.v1 import AppTest

PAGES = ["overview", "simulator", "forecast", "anomalies", "weekly_report", "methods"]


@pytest.mark.parametrize("page", PAGES)
def test_every_page_renders_from_the_committed_snapshots_without_a_database(page, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://nowhere.invalid/none")     # any database call would fail
    at = AppTest.from_file(f"../app/{page}.py", default_timeout=60).run()
    assert not at.exception


def test_simulator_reacts_to_the_cap():
    at = AppTest.from_file("../app/simulator.py", default_timeout=60).run()
    at.slider[0].set_value(0.10).run()
    assert not at.exception
    assert any("profitable today" in m.value for m in at.markdown)       # a 10% cap reaches profitable levels
