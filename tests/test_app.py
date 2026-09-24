from pathlib import Path

from streamlit.testing.v1 import AppTest


def test_demo_mode_renders_complete_report():
    app_path = Path(__file__).parents[1] / "app.py"
    app = AppTest.from_file(app_path, default_timeout=15).run()
    assert not app.exception
    assert app.title[0].value == "ProfileLens"

    app.button[0].click().run()

    assert not app.exception
    assert [tab.label for tab in app.tabs] == ["Evidence table", "Methodology", "Export"]
    metrics = {metric.label: metric.value for metric in app.metric}
    assert metrics == {
        "Archived": "5",
        "Public listing": "2",
        "Live, not listed": "1",
        "Direct checks": "4",
    }
