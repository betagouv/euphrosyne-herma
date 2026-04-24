from data_upload import config as config_module


def test_load_config_reads_yaml(monkeypatch, tmp_path):
    config_path = tmp_path / "config.yml"
    config_path.write_text(
        """
default-environment: euphrosyne
environments:
  euphrosyne:
    url: "https://euphrosyne.example"
    euphro-tools-url: "https://tools.example"
  euphrosyne-staging:
    url: "https://staging.euphrosyne.example"
    euphro-tools-url: "https://staging.tools.example"
""".lstrip()
    )
    monkeypatch.setattr(config_module, "DEFAULT_CONFIG_PATH", str(config_path))

    assert config_module.load_config() == {
        "default-environment": "euphrosyne",
        "environments": {
            "euphrosyne": {
                "url": "https://euphrosyne.example",
                "euphro-tools-url": "https://tools.example",
            },
            "euphrosyne-staging": {
                "url": "https://staging.euphrosyne.example",
                "euphro-tools-url": "https://staging.tools.example",
            },
        },
    }


def test_resolve_config_uses_default_environment(monkeypatch, tmp_path):
    config_path = tmp_path / "config.yml"
    config_path.write_text(
        """
default-environment: euphrosyne
environments:
  euphrosyne:
    url: "https://euphrosyne.example"
    euphro-tools-url: "https://tools.example"
  euphrosyne-staging:
    url: "https://staging.euphrosyne.example"
    euphro-tools-url: "https://staging.tools.example"
""".lstrip()
    )
    monkeypatch.setattr(config_module, "DEFAULT_CONFIG_PATH", str(config_path))
    monkeypatch.delenv("EUPHROSYNE_URL", raising=False)

    loaded_config = config_module.load_config()

    assert config_module.resolve_config(loaded_config) == {
        "environment": "euphrosyne",
        "euphrosyne": {"url": "https://euphrosyne.example"},
        "euphrosyne-tools": {"url": "https://tools.example"},
    }


def test_resolve_config_overrides_euphrosyne_url_from_environment(
    monkeypatch, tmp_path
):
    config_path = tmp_path / "config.yml"
    config_path.write_text(
        """
default-environment: euphrosyne
environments:
  euphrosyne:
    url: "https://euphrosyne.example"
    euphro-tools-url: "https://tools.example"
  euphrosyne-staging:
    url: "https://staging.euphrosyne.example"
    euphro-tools-url: "https://staging.tools.example"
""".lstrip()
    )
    monkeypatch.setattr(config_module, "DEFAULT_CONFIG_PATH", str(config_path))
    monkeypatch.setenv("EUPHROSYNE_URL", "https://override.example")

    loaded_config = config_module.load_config()

    assert config_module.resolve_config(loaded_config, "euphrosyne-staging") == {
        "environment": "euphrosyne-staging",
        "euphrosyne": {"url": "https://override.example"},
        "euphrosyne-tools": {"url": "https://staging.tools.example"},
    }
