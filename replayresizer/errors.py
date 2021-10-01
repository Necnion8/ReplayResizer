import subprocess


class ProcessCodeError(Exception):
    def __init__(self, process: subprocess.Popen, lines: str = ""):
        self.process = process
        self.lines = lines

    @property
    def return_code(self):
        return self.process.returncode
