import os
import typing

import yaml

from data_upload.utils import BUNDLE_DIR, IS_BUNDLED

if IS_BUNDLED:
    DEFAULT_CONFIG_PATH = str(BUNDLE_DIR / "config.yml")
else:
    DEFAULT_CONFIG_PATH = str(BUNDLE_DIR / ".." / "config.yml")


class EuphrosyneConfig(typing.TypedDict):
    url: str
    api_key: str


class Config(typing.TypedDict):
    euphrosyne: EuphrosyneConfig


def load_config() -> Config:
    # Load defaults from YAML
    with open(DEFAULT_CONFIG_PATH, "r") as f:
        config = yaml.safe_load(f)

    # Override with environment variables if present
    config["euphrosyne"]["url"] = os.environ.get(
        "EUPHROSYNE_URL", config["euphrosyne"]["url"]
    )
    return config
