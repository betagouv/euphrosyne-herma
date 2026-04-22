from data_upload import config as config_module


def test_load_config_reads_yaml(monkeypatch, tmp_path):
    config_path = tmp_path / "config.yml"
    config_path.write_text(
        """
euphrosyne:
  url: "https://euphrosyne.example"
euphrosyne-tools:
  url: "https://tools.example"
""".lstrip()
    )
    monkeypatch.setattr(config_module, "DEFAULT_CONFIG_PATH", str(config_path))
    monkeypatch.delenv("EUPHROSYNE_URL", raising=False)

    assert config_module.load_config() == {
        "euphrosyne": {"url": "https://euphrosyne.example"},
        "euphrosyne-tools": {"url": "https://tools.example"},
    }


def test_load_config_overrides_euphrosyne_url_from_environment(monkeypatch, tmp_path):
    config_path = tmp_path / "config.yml"
    config_path.write_text(
        """
euphrosyne:
  url: "https://euphrosyne.example"
euphrosyne-tools:
  url: "https://tools.example"
""".lstrip()
    )
    monkeypatch.setattr(config_module, "DEFAULT_CONFIG_PATH", str(config_path))
    monkeypatch.setenv("EUPHROSYNE_URL", "https://override.example")

    loaded_config = config_module.load_config()

    assert loaded_config["euphrosyne"]["url"] == "https://override.example"
    assert loaded_config["euphrosyne-tools"]["url"] == "https://tools.example"
