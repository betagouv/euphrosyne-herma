import platform
import subprocess
import sys
import zipfile
from pathlib import Path

import httpx

from data_upload.utils import IS_BUNDLED, BUNDLE_DIR

if IS_BUNDLED:
    _bin_folder = BUNDLE_DIR / "bin"
else:
    _bin_folder = Path(__file__).parent / ".." / "bin"


_is_64bits = sys.maxsize > 2**32

_os = platform.system()
_is_windows = _os == "Windows"
_is_macos = _os == "Darwin"

azcopy_path = None
if _is_windows:
    azcopy_path = _bin_folder / "azcopy" / "azcopy.exe"
elif _is_macos:
    azcopy_path = _bin_folder / "azcopy" / "azcopy"


def get_copy_command(src: str, dest: str, sas_token: str) -> list[str]:
    """Get the command to copy the contents of a folder to a destination."""
    if not Path(src).exists():
        raise FileNotFoundError(f"Source folder {src} does not exist.")
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
    if not azcopy_path or not azcopy_path.exists():
        return False
    try:
        subprocess.run([azcopy_path, "--version"], check=True)
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False


def download_azcopy():
    """Download AzCopy if not installed."""
    if not azcopy_path.exists():
        print("AzCopy not found, downloading...")
        # Here you would implement the download logic, e.g., using requests or wget.
        # For now, we will just create an empty file to simulate the download.
        _bin_folder.touch()
        zip_path = None
        if _is_macos:
            zip_path = _download_mac_azcopy()
        elif _is_windows:
            zip_path = _download_windows_azcopy()
        else:
            raise NotImplementedError(f"AzCopy download not implemented for {_os}.")
        _unzip_azcopy(zip_path)
        print(f"AzCopy downloaded to {_bin_folder}")

        if _os == "Darwin":
            # Make the binary executable on macOS
            print("Making AzCopy executable...")
            subprocess.run(["chmod", "+x", str(azcopy_path)], check=True)

        if not is_azcopy_installed():
            raise RuntimeError("AzCopy installation failed. Please check the logs.")
        print("AzCopy installation successful.")
    else:
        print("AzCopy is already installed.")


def _unzip_azcopy(zip_path):
    """Unzip the downloaded AzCopy binary."""
    print(f"Unzipping AzCopy from {zip_path}...")
    with zipfile.ZipFile(zip_path, "r") as zip_ref:
        first_member = zip_ref.namelist()[0]
        zip_ref.extractall(_bin_folder)
        extracted_path = _bin_folder / first_member
        renamed_path = _bin_folder / "azcopy"
        if extracted_path.exists():
            extracted_path.rename(renamed_path)
    print(f"AzCopy extracted to {_bin_folder}")
    zip_path.unlink()  # Optionally remove the zip file after extraction


def _download_mac_azcopy():
    """Download AzCopy for macOS."""
    print("Downloading AzCopy for macOS...")
    url = "https://aka.ms/downloadazcopy-v10-mac"
    zip_path = (_bin_folder / "azcopy").with_suffix(".zip")
    _download_binary(
        url,
        zip_path,
    )
    return zip_path


def _download_windows_azcopy():
    """Download AzCopy for Windows."""
    print("Downloading AzCopy for Windows...")
    # Implement the actual download logic here
    url = (
        "https://aka.ms/downloadazcopy-v10-windows"
        if _is_64bits
        else "https://aka.ms/downloadazcopy-v10-windows-32bit"
    )
    zip_path = (_bin_folder / "azcopy").with_suffix(".zip")
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
