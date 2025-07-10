import subprocess

from PySide6.QtCore import QObject, Signal, Slot

from data_upload.azcopy import get_copy_command


class ProcessWorker(QObject):
    output_signal = Signal(str)
    finished_signal = Signal(int)

    def __init__(self, src: str, dest: str, sas_token: str):
        super().__init__()
        self.cmd = get_copy_command(src, dest, sas_token)

    @Slot()
    def run(self):
        process = subprocess.Popen(
            self.cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        for line in process.stdout:
            self.output_signal.emit(line.rstrip())
        process.stdout.close()
        process.wait()
        self.finished_signal.emit(process.returncode)
