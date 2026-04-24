import platform
import subprocess
import sys
import zipfile
from pathlib import Path

import httpx
from PySide6.QtCore import QStandardPaths

from data_upload.utils import BUNDLE_DIR, IS_BUNDLED

_is_64bits = sys.maxsize > 2**32

_os = platform.system()
_is_windows = _os == "Windows"
_is_macos = _os == "Darwin"


def _get_bin_folder() -> Path:
    if IS_BUNDLED and _is_macos:
        app_data_location = QStandardPaths.writableLocation(
            QStandardPaths.AppLocalDataLocation
        )
        if not app_data_location:
            raise RuntimeError(
                "Could not determine a writable application data directory for AzCopy."
            )
        return Path(app_data_location) / "bin"

    if IS_BUNDLED:
        return BUNDLE_DIR / "bin"

    return Path(__file__).resolve().parent.parent / "bin"


def get_azcopy_path() -> Path | None:
    bin_folder = _get_bin_folder()

    if _is_windows:
        return bin_folder / "azcopy" / "azcopy.exe"
    if _is_macos:
        return bin_folder / "azcopy" / "azcopy"
    return None


def get_copy_command(src: str, dest: str, sas_token: str) -> list[str]:
    """Get the command to copy the contents of a folder to a destination."""
    if not Path(src).exists():
        raise FileNotFoundError(f"Source folder {src} does not exist.")
    azcopy_path = get_azcopy_path()
    if not is_azcopy_installed():
        raise RuntimeError("AzCopy is not installed. Please install it first.")
    return [
        str(azcopy_path),
        "copy",
        src + "/*",
        f"{dest}?{sas_token}",
        "--recursive",
    ]


def is_azcopy_installed() -> bool:
    """Check if AzCopy is installed."""
    azcopy_path = get_azcopy_path()
    if not azcopy_path or not azcopy_path.exists():
        return False
    try:
        subprocess.run([azcopy_path, "--version"], check=True)
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False


def download_azcopy():
    """Download AzCopy if not installed."""
    azcopy_path = get_azcopy_path()
    if azcopy_path is None:
        raise NotImplementedError(f"AzCopy download not implemented for {_os}.")

    if not azcopy_path.exists():
        print("AzCopy not found, downloading...")
        bin_folder = _get_bin_folder()
        bin_folder.mkdir(parents=True, exist_ok=True)
        zip_path = None
        if _is_macos:
            zip_path = _download_mac_azcopy(bin_folder)
        elif _is_windows:
            zip_path = _download_windows_azcopy(bin_folder)
        _unzip_azcopy(zip_path, bin_folder)
        print(f"AzCopy downloaded to {bin_folder}")

        if _os == "Darwin":
            # Make the binary executable on macOS
            print("Making AzCopy executable...")
            subprocess.run(["chmod", "+x", str(azcopy_path)], check=True)

        if not is_azcopy_installed():
            raise RuntimeError("AzCopy installation failed. Please check the logs.")
        print("AzCopy installation successful.")
    else:
        print("AzCopy is already installed.")


def _unzip_azcopy(zip_path: Path, bin_folder: Path):
    """Unzip the downloaded AzCopy binary."""
    print(f"Unzipping AzCopy from {zip_path}...")
    with zipfile.ZipFile(zip_path, "r") as zip_ref:
        first_member = zip_ref.namelist()[0]
        zip_ref.extractall(bin_folder)
        extracted_path = bin_folder / first_member
        renamed_path = bin_folder / "azcopy"
        if extracted_path.exists():
            extracted_path.rename(renamed_path)
    print(f"AzCopy extracted to {bin_folder}")
    zip_path.unlink()  # Optionally remove the zip file after extraction


def _download_mac_azcopy(bin_folder: Path) -> Path:
    """Download AzCopy for macOS."""
    print("Downloading AzCopy for macOS...")
    url = "https://aka.ms/downloadazcopy-v10-mac"
    zip_path = (bin_folder / "azcopy").with_suffix(".zip")
    _download_binary(
        url,
        zip_path,
    )
    return zip_path


def _download_windows_azcopy(bin_folder: Path) -> Path:
    """Download AzCopy for Windows."""
    print("Downloading AzCopy for Windows...")
    url = (
        "https://aka.ms/downloadazcopy-v10-windows"
        if _is_64bits
        else "https://aka.ms/downloadazcopy-v10-windows-32bit"
    )
    zip_path = (bin_folder / "azcopy").with_suffix(".zip")
    _download_binary(
        url,
        zip_path,
    )
    return zip_path


def _download_binary(url, dest_path):
    with httpx.stream("GET", url, follow_redirects=True) as response:
        response.raise_for_status()
        with open(dest_path, "wb") as f:
            for chunk in response.iter_bytes(chunk_size=8192):
                if chunk:
                    f.write(chunk)
