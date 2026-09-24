import json

from profilelens.cli import main


def test_demo_cli_writes_json(tmp_path):
    destination = tmp_path / "demo.json"
    result = main(["--demo", "--output", str(destination)])
    assert result == 0
    assert (
        json.loads(destination.read_text(encoding="utf-8"))["metadata"]["username"]
        == "demo_account"
    )


def test_cli_requires_authorized_use_acknowledgement():
    assert main(["test_user"]) == 2
