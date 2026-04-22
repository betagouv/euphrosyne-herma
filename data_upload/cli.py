import argparse
import getpass
import logging
import subprocess
import sys
from pathlib import Path

import httpx
from PySide6.QtCore import QSettings

from data_upload.azcopy import download_azcopy, get_copy_command, is_azcopy_installed
from data_upload.config import load_config
from data_upload.euphro_tools import (
    EuphrosyneToolsConnectionError,
    EuphrosyneToolsService,
    InitFoldersError,
)
from data_upload.euphrosyne.auth import (
    EuphrosyneAuth,
    EuphrosyneAuthenticationError,
    EuphrosyneConnectionError,
    euphrosyne_login,
    save_refresh_token,
)

logger = logging.getLogger(__name__)

DATA_TYPES = {
    "raw-data": "raw_data",
    "processed-data": "processed_data",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Upload a data folder to an Euphrosyne run from the terminal."
    )
    parser.add_argument("--project", required=True, help="Euphrosyne project name")
    parser.add_argument("--run", required=True, help="Euphrosyne run label")
    parser.add_argument(
        "--data-type",
        required=True,
        choices=sorted(DATA_TYPES),
        help="Type of run data to upload",
    )
    parser.add_argument(
        "--data-path",
        required=True,
        help="Existing local data folder to upload",
    )
    parser.add_argument("--email", help="Euphrosyne account email")
    parser.add_argument("--log", default="INFO", help="Log level (default: INFO)")
    return parser


def _configure_logging(level_name: str):
    numeric_level = getattr(logging, level_name.upper(), None)
    if not isinstance(numeric_level, int):
        raise ValueError(f"Invalid log level: {level_name}")
    logging.basicConfig(level=numeric_level)


def _validate_data_path(data_path: str) -> Path:
    path = Path(data_path)
    if not path.is_dir():
        raise ValueError(f"Data path must be an existing directory: {data_path}")
    return path


def _login(config, settings: QSettings, email: str | None) -> tuple[str, str]:
    if not email:
        email = input("Email: ")
    password = getpass.getpass("Password: ")

    tokens = euphrosyne_login(
        host=config["euphrosyne"]["url"],
        email=email,
        password=password,
    )
    if tokens is None:
        raise EuphrosyneAuthenticationError(
            "Login failed. Please check your credentials."
        )

    access_token, refresh_token = tokens
    settings.setValue("access_token", access_token)
    save_refresh_token(settings, refresh_token)
    return access_token, refresh_token


def _ensure_azcopy_installed():
    if not is_azcopy_installed():
        logger.info("AzCopy not found; downloading...")
        download_azcopy()


def run_upload(args: argparse.Namespace) -> int:
    _configure_logging(args.log)
    data_path = _validate_data_path(args.data_path)
    config = load_config()
    settings = QSettings("Euphrosyne", "Herma")
    access_token, refresh_token = _login(config, settings, args.email)
    _ensure_azcopy_installed()

    tools_service = EuphrosyneToolsService(
        host=config["euphrosyne-tools"]["url"],
        auth=EuphrosyneAuth(
            access_token=access_token,
            refresh_token=refresh_token,
            host=config["euphrosyne"]["url"],
            settings=settings,
        ),
    )
    tools_service.init_folders(args.project, args.run)
    credentials = tools_service.get_run_data_upload_shared_access_signature(
        project_name=args.project,
        run_name=args.run,
        data_type=DATA_TYPES[args.data_type],
    )
    command = get_copy_command(str(data_path), credentials["url"], credentials["token"])
    completed_process = subprocess.run(command)
    return completed_process.returncode


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        return run_upload(args)
    except (
        EuphrosyneAuthenticationError,
        EuphrosyneConnectionError,
        EuphrosyneToolsConnectionError,
        FileNotFoundError,
        InitFoldersError,
        RuntimeError,
        ValueError,
        httpx.HTTPError,
        OSError,
    ) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
