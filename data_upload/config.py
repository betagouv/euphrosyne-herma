import os
import typing

import yaml

from data_upload.utils import BUNDLE_DIR, IS_BUNDLED

if IS_BUNDLED:
    DEFAULT_CONFIG_PATH = str(BUNDLE_DIR / "config.yml")
else:
    DEFAULT_CONFIG_PATH = str(BUNDLE_DIR / ".." / "config.yml")

ENVIRONMENT_SETTING_KEY = "environment"


class EuphrosyneConfig(typing.TypedDict):
    url: str


EnvironmentCatalogEntry = typing.TypedDict(
    "EnvironmentCatalogEntry",
    {
        "url": str,
        "euphro-tools-url": str,
    },
)


ConfigCatalog = typing.TypedDict(
    "ConfigCatalog",
    {
        "default-environment": str,
        "environments": dict[str, EnvironmentCatalogEntry],
    },
)


Config = typing.TypedDict(
    "Config",
    {
        "environment": str,
        "euphrosyne": EuphrosyneConfig,
        "euphrosyne-tools": EuphrosyneConfig,
    },
)


def load_config() -> ConfigCatalog:
    with open(DEFAULT_CONFIG_PATH, "r") as f:
        return yaml.safe_load(f)


def list_environment_keys(config: ConfigCatalog) -> list[str]:
    return list(config["environments"])


def get_environment_label(environment: str) -> str:
    parts = environment.split("-")
    if not parts:
        return environment
    return " ".join([parts[0].capitalize(), *parts[1:]])


def resolve_environment_name(
    config: ConfigCatalog, environment: str | None = None
) -> str:
    if environment in config["environments"]:
        return typing.cast(str, environment)
    return config["default-environment"]


def resolve_config(config: ConfigCatalog, environment: str | None = None) -> Config:
    environment_name = resolve_environment_name(config, environment)
    active_environment = config["environments"][environment_name]
    return {
        "environment": environment_name,
        "euphrosyne": {
            "url": os.environ.get("EUPHROSYNE_URL", active_environment["url"])
        },
        "euphrosyne-tools": {"url": active_environment["euphro-tools-url"]},
    }
