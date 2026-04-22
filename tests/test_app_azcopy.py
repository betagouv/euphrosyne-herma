import subprocess

import pytest

from data_upload.app import azcopy as app_azcopy


class FakeStdout:
    def __init__(self, lines):
        self.lines = lines
        self.closed = False

    def __iter__(self):
        return iter(self.lines)

    def close(self):
        self.closed = True


class FakeProcess:
    def __init__(self, returncode):
        self.stdout = FakeStdout(["first line\n", "second line\n"])
        self.returncode = returncode
        self.wait_called = False

    def wait(self):
        self.wait_called = True


@pytest.mark.parametrize("returncode", [0, 1])
def test_process_worker_emits_output_and_return_code(monkeypatch, returncode):
    process = FakeProcess(returncode)
    popen_calls = []

    def fake_popen(*args, **kwargs):
        popen_calls.append((args, kwargs))
        return process

    monkeypatch.setattr(
        app_azcopy, "get_copy_command", lambda src, dest, sas_token: ["azcopy", "copy"]
    )
    monkeypatch.setattr(app_azcopy.subprocess, "Popen", fake_popen)
    emitted_output = []
    emitted_return_codes = []

    worker = app_azcopy.ProcessWorker(
        src="/tmp/source",
        dest="https://storage.example/share",
        sas_token="sas-token",
    )
    worker.output_signal.connect(emitted_output.append)
    worker.finished_signal.connect(emitted_return_codes.append)

    worker.run()

    assert emitted_output == ["first line", "second line"]
    assert emitted_return_codes == [returncode]
    assert process.stdout.closed is True
    assert process.wait_called is True
    assert popen_calls == [
        (
            (["azcopy", "copy"],),
            {
                "stdout": subprocess.PIPE,
                "stderr": subprocess.STDOUT,
                "text": True,
                "bufsize": 1,
            },
        )
    ]
