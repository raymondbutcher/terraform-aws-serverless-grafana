from subprocess import Popen

from install import INSTALL_PATH, BIN_PATH, CONFIG_PATH


def start_grafana():
    return Popen((
        BIN_PATH,
        '-homepath', INSTALL_PATH,
        '-config', CONFIG_PATH,
    ))


def stop_grafana(process):
    process.terminate()
    process.wait(timeout=5)
