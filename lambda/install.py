import os
import shutil
import subprocess

from botocore.vendored.requests import Session
from botocore.vendored.requests.adapters import HTTPAdapter
from botocore.vendored.requests.packages.urllib3.util.retry import Retry


BIN_PATH = '/tmp/grafana/bin/grafana-server'
CONFIG_PATH = '/tmp/grafana.conf'
DOWNLOAD_URL = 'https://s3-us-west-2.amazonaws.com/grafana-releases/release/grafana-4.6.3.linux-x64.tar.gz'
DOWNLOAD_PATH = '/tmp/grafana.tar.gz'
EXTRACTED_PATH = '/tmp/grafana-4.6.3'
INSTALL_PATH = '/tmp/grafana'

CONFIG_TEMPLATE = '''
[server]
domain = {domain}
root_url = %(protocol)s://%(domain)s:/{stage}/grafana
'''.lstrip()


def install_grafana():

    if os.path.exists(INSTALL_PATH):
        print('Found {}'.format(INSTALL_PATH))
        return

    if not os.path.exists(DOWNLOAD_PATH):
        print('Downloading {}'.format(DOWNLOAD_URL))
        download_session = Session()
        download_session.mount('', HTTPAdapter(max_retries=Retry(
            total=10,
            backoff_factor=0.5,
        )))
        response = download_session.get(DOWNLOAD_URL, stream=True)
        with open(DOWNLOAD_PATH, 'wb') as download_file:
            shutil.copyfileobj(response.raw, download_file)

    if os.path.exists(EXTRACTED_PATH):
        print('Cleaning up {}'.format(EXTRACTED_PATH))
        shutil.rmtree(EXTRACTED_PATH)

    print('Extracting {}'.format(DOWNLOAD_PATH))
    subprocess.check_call(('tar', '-xf', DOWNLOAD_PATH, '-C', '/tmp'))

    print('Renaming {}'.format(EXTRACTED_PATH))
    os.rename(EXTRACTED_PATH, INSTALL_PATH)

    print('Installed {}'.format(INSTALL_PATH))


def configure_grafana(event):
    with open(CONFIG_PATH, 'wt') as config_file:
        config_file.write(CONFIG_TEMPLATE.format(
            domain=event['headers']['Host'],
            stage=event['requestContext']['stage'],
        ))
