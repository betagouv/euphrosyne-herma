from data_upload import cli as cli_module
from data_upload import gui as gui_module
from data_upload import main as main_module


def test_main_launches_gui_without_upload_args(monkeypatch):
    gui_calls = []
    cli_calls = []
    monkeypatch.setattr(
        gui_module.ConverterGUI,
        "start",
        lambda: gui_calls.append("started"),
    )
    monkeypatch.setattr(cli_module, "main", lambda argv: cli_calls.append(argv))

    exit_code = main_module.main([])

    assert exit_code == 0
    assert gui_calls == ["started"]
    assert cli_calls == []


def test_main_delegates_to_cli_when_upload_args_are_present(monkeypatch, tmp_path):
    data_path = tmp_path / "data"
    data_path.mkdir()
    cli_calls = []
    argv = [
        "--project",
        "Project A",
        "--run",
        "Run 1",
        "--data-type",
        "raw-data",
        "--data-path",
        str(data_path),
    ]
    monkeypatch.setattr(cli_module, "main", lambda args: cli_calls.append(args) or 7)

    exit_code = main_module.main(argv)

    assert exit_code == 7
    assert cli_calls == [argv]

