import subprocess
from pathlib import Path

import httpx
import pytest

from data_upload import azcopy


def test_get_copy_command_builds_recursive_command(monkeypatch, tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    binary = tmp_path / "bin" / "azcopy"
    binary.parent.mkdir()
    binary.write_text("binary")
    monkeypatch.setattr(azcopy, "azcopy_path", binary)
    monkeypatch.setattr(azcopy, "is_azcopy_installed", lambda: True)

    command = azcopy.get_copy_command(
        str(source), "https://storage.example/share", "sas-token"
    )

    assert command == [
        str(binary),
        "copy",
        f"{source}/*",
        "https://storage.example/share?sas-token",
        "--recursive",
    ]


def test_get_copy_command_raises_when_source_does_not_exist(monkeypatch, tmp_path):
    binary = tmp_path / "azcopy"
    monkeypatch.setattr(azcopy, "azcopy_path", binary)
    monkeypatch.setattr(azcopy, "is_azcopy_installed", lambda: True)

    with pytest.raises(FileNotFoundError):
        azcopy.get_copy_command(
            str(tmp_path / "missing"), "https://storage.example/share", "sas-token"
        )


def test_get_copy_command_raises_when_azcopy_is_missing(monkeypatch, tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    monkeypatch.setattr(azcopy, "is_azcopy_installed", lambda: False)

    with pytest.raises(RuntimeError, match="AzCopy is not installed"):
        azcopy.get_copy_command(
            str(source), "https://storage.example/share", "sas-token"
        )


def test_is_azcopy_installed_returns_false_when_path_is_not_configured(monkeypatch):
    monkeypatch.setattr(azcopy, "azcopy_path", None)

    assert azcopy.is_azcopy_installed() is False


def test_is_azcopy_installed_runs_version_check(monkeypatch, tmp_path):
    binary = tmp_path / "azcopy"
    binary.write_text("binary")
    calls = []

    def fake_run(command, check):
        calls.append((command, check))
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(azcopy, "azcopy_path", binary)
    monkeypatch.setattr(azcopy.subprocess, "run", fake_run)

    assert azcopy.is_azcopy_installed() is True
    assert calls == [([binary, "--version"], True)]


def test_is_azcopy_installed_returns_false_when_version_check_fails(
    monkeypatch, tmp_path
):
    binary = tmp_path / "azcopy"
    binary.write_text("binary")

    def fake_run(command, check):
        raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(azcopy, "azcopy_path", binary)
    monkeypatch.setattr(azcopy.subprocess, "run", fake_run)

    assert azcopy.is_azcopy_installed() is False


def test_download_azcopy_downloads_unzips_and_marks_macos_binary_executable(
    monkeypatch, tmp_path
):
    bin_folder = tmp_path / "bin"
    archive = tmp_path / "azcopy.zip"
    chmod_calls = []

    def fake_download_mac_azcopy():
        archive.write_text("zip")
        return archive

    def fake_unzip_azcopy(zip_path):
        assert zip_path == archive
        (bin_folder / "azcopy").mkdir(parents=True)
        (bin_folder / "azcopy" / "azcopy").write_text("binary")
        archive.unlink()

    def fake_run(command, check):
        chmod_calls.append((command, check))
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(azcopy, "_bin_folder", bin_folder)
    monkeypatch.setattr(azcopy, "azcopy_path", bin_folder / "azcopy" / "azcopy")
    monkeypatch.setattr(azcopy, "_is_macos", True)
    monkeypatch.setattr(azcopy, "_is_windows", False)
    monkeypatch.setattr(azcopy, "_os", "Darwin")
    monkeypatch.setattr(azcopy, "_download_mac_azcopy", fake_download_mac_azcopy)
    monkeypatch.setattr(azcopy, "_unzip_azcopy", fake_unzip_azcopy)
    monkeypatch.setattr(azcopy.subprocess, "run", fake_run)

    azcopy.download_azcopy()

    assert chmod_calls == [
        (["chmod", "+x", str(bin_folder / "azcopy" / "azcopy")], True),
        ([bin_folder / "azcopy" / "azcopy", "--version"], True),
    ]


def test_download_azcopy_raises_for_unsupported_os(monkeypatch, tmp_path):
    monkeypatch.setattr(azcopy, "azcopy_path", tmp_path / "azcopy")
    monkeypatch.setattr(azcopy, "_bin_folder", tmp_path / "bin")
    monkeypatch.setattr(azcopy, "_is_macos", False)
    monkeypatch.setattr(azcopy, "_is_windows", False)
    monkeypatch.setattr(azcopy, "_os", "Linux")

    with pytest.raises(NotImplementedError, match="Linux"):
        azcopy.download_azcopy()


def test_download_binary_streams_response_to_file(monkeypatch, tmp_path):
    destination = tmp_path / "azcopy.zip"

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def raise_for_status(self):
            return None

        def iter_bytes(self, chunk_size):
            assert chunk_size == 8192
            yield b"abc"
            yield b""
            yield b"def"

    def fake_stream(method, url, follow_redirects):
        assert method == "GET"
        assert url == "https://download.example/azcopy.zip"
        assert follow_redirects is True
        return FakeResponse()

    monkeypatch.setattr(azcopy.httpx, "stream", fake_stream)

    azcopy._download_binary("https://download.example/azcopy.zip", destination)

    assert destination.read_bytes() == b"abcdef"


def test_download_binary_raises_http_errors(monkeypatch, tmp_path):
    destination = tmp_path / "azcopy.zip"

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def raise_for_status(self):
            raise httpx.HTTPStatusError(
                "download failed",
                request=httpx.Request("GET", "https://download.example/azcopy.zip"),
                response=httpx.Response(500),
            )

    monkeypatch.setattr(
        azcopy.httpx,
        "stream",
        lambda method, url, follow_redirects: FakeResponse(),
    )

    with pytest.raises(httpx.HTTPStatusError):
        azcopy._download_binary("https://download.example/azcopy.zip", destination)
