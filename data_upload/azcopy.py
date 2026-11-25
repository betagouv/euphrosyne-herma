import platform
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path, PurePosixPath, PureWindowsPath

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


def _is_unsafe_member(name: str) -> bool:
    normalized = name.replace("\\", "/")
    windows_path = PureWindowsPath(name)
    return (
        normalized.startswith("/")
        or windows_path.is_absolute()
        or windows_path.drive != ""
        or ".." in PurePosixPath(normalized).parts
    )


def _unzip_azcopy(zip_path: Path, bin_folder: Path):
    """Extract only the AzCopy binary into ``bin_folder/azcopy/``.

    Archive members with absolute paths or ``..`` components are refused, and the
    destination is checked to stay inside ``bin_folder``.
    """
    print(f"Unzipping AzCopy from {zip_path}...")
    binary_name = "azcopy.exe" if _is_windows else "azcopy"
    target_dir = bin_folder / "azcopy"
    destination = target_dir / binary_name
    if not destination.resolve().is_relative_to(bin_folder.resolve()):
        raise ValueError(f"Unsafe AzCopy destination: {destination}")

    with zipfile.ZipFile(zip_path, "r") as zip_ref:
        members = zip_ref.infolist()
        for member in members:
            if _is_unsafe_member(member.filename):
                raise ValueError(f"Unsafe path in AzCopy archive: {member.filename}")
        binary_member = next(
            (
                m
                for m in members
                if not m.is_dir()
                and PurePosixPath(m.filename.replace("\\", "/")).name == binary_name
            ),
            None,
        )
        if binary_member is None:
            raise RuntimeError(f"{binary_name} not found in AzCopy archive.")
        target_dir.mkdir(parents=True, exist_ok=True)
        with zip_ref.open(binary_member) as src, open(destination, "wb") as dst:
            shutil.copyfileobj(src, dst)
    print(f"AzCopy extracted to {target_dir}")
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
