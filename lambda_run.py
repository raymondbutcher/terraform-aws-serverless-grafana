import os
import re
import tempfile
from base64 import b64decode, b64encode
from contextlib import contextmanager
from subprocess import Popen
from botocore.vendored.requests import Session
from botocore.vendored.requests.adapters import HTTPAdapter
from botocore.vendored.requests.packages.urllib3.util.retry import Retry


LAMBDA_BUILD_FUNCTION_NAME = os.environ['LAMBDA_BUILD_FUNCTION_NAME']

LAMBDA_HOME = os.path.dirname(__file__)
GRAFANA_HOME = os.path.join(LAMBDA_HOME, 'grafana')
GRAFANA_BIN_PATH = os.path.join(GRAFANA_HOME, 'bin', 'grafana-server')

CONFIG_TEMPLATE = '''
[server]
domain = {domain}
root_url = %(protocol)s://%(domain)s:/{stage}/grafana

[paths]
data = /tmp/grafana/data
logs = /tmp/grafana/logs

[auth]
disable_login_form = true
disable_signout_menu = true

[auth.anonymous]
enabled = true

'''.lstrip()

URL_PREFIX_RE = re.compile('^/grafana')

# Use retries when proxying requests to the Grafana process,
# because it can take a moment for it to start listening.
requests = Session()
requests.mount('http://', HTTPAdapter(max_retries=Retry(
    connect=20,
    backoff_factor=0.1,
)))


@contextmanager
def configure_grafana(event):
    """
    Write a configuration file to fix URLs so they're relative
    to the API Gateway URLs.

    """

    with tempfile.NamedTemporaryFile() as temp_file:
        with open(temp_file.name, 'wt') as config_file:
            config_file.write(CONFIG_TEMPLATE.format(
                domain=event['headers']['Host'],
                stage=event['requestContext']['stage'],
            ))
        yield temp_file.name


def grafana_start(config_path):
    return Popen((
        GRAFANA_BIN_PATH,
        '-homepath', GRAFANA_HOME,
        '-config', config_path,
    ))


def grafana_stop(process):
    process.terminate()
    process.wait(timeout=5)


@contextmanager
def lock(context):
    """
    Lock the data so that only 1 Lambda function can read/write at a time.

    """

    seconds = int(context.get_remaining_time_in_millis() / 1000)
    print('todo: dynamodb: acquire lock for {} seconds'.format(seconds))
    try:
        yield
    finally:
        print('todo: dynamodb: release lock')


def proxy_request(event):

    path = URL_PREFIX_RE.sub('', event['path'])

    print('path is', path)
    if path.startswith('/public/'):
        local_path = os.path.join(GRAFANA_HOME, path)
        print('todo: serve from', local_path)

    url = 'http://127.0.0.1:3000' + path

    if event['isBase64Encoded']:
        request_body = b64decode(event['body'])
    else:
        request_body = None

    response = requests.request(
        method=event['httpMethod'],
        url=url,
        data=request_body,
        headers=event['headers'],
        allow_redirects=False,
    )

    if response.encoding:
        body = response.text
        is_binary = False
    else:
        body = b64encode(response.content).decode('utf-8')
        is_binary = True

    headers = response.headers
    headers.pop('transfer-encoding', None)
    headers['Content-Length'] = len(body)

    print(headers, 'isBase64Encoded:', is_binary)

    return {
        'body': body,
        'headers': dict(headers),
        'statusCode': response.status_code,
        'isBase64Encoded': is_binary,
    }


def sync(download=False, upload=False):

    if download:
        print('todo: dynamodb: get data versions/hashes')
        print('todo: s3: download changed data')

    if upload:
        print('todo: s3: upload changed data')
        import subprocess
        subprocess.check_call(('find', '/tmp'))


def lambda_handler(event, context):
    print(event)

    if not os.path.exists(GRAFANA_HOME):
        print('todo: run function {}'.format(LAMBDA_BUILD_FUNCTION_NAME))
        raise NotImplementedError('todo: trigger build lambda, return error')

    with configure_grafana(event) as config_path:
        with lock(context):
            sync(download=True)
            process = grafana_start(config_path)
            response = proxy_request(event)
            grafana_stop(process)
            sync(upload=True)
    return response
