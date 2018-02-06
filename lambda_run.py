import boto3
import os
import re

from base64 import b64decode, b64encode
from contextlib import contextmanager
from math import ceil
from subprocess import Popen
from time import sleep, time

from botocore.exceptions import ClientError
from botocore.vendored.requests import Session
from botocore.vendored.requests.adapters import HTTPAdapter
from botocore.vendored.requests.packages.urllib3.util.retry import Retry


LAMBDA_BUILD_FUNCTION_NAME = os.environ['LAMBDA_BUILD_FUNCTION_NAME']

LOCK_TABLE_NAME = os.environ['LOCK_TABLE_NAME']
LOCK_ID = '1'

PATH_PREFIX_RE = re.compile('^/grafana')

GRAFANA_HOME = os.path.join(os.path.dirname(__file__), 'grafana')
GRAFANA_BIN = os.path.join(GRAFANA_HOME, 'bin', 'grafana-server')
GRAFANA_CONFIG = '/tmp/grafana.conf'
GRAFANA_CONFIG_TEMPLATE = '''
[server]
domain = {domain}
root_url = %(protocol)s://%(domain)s:/{stage}/grafana

[paths]
data = /tmp/grafana/data
logs = /tmp/grafana/logs
plugins = /tmp/grafana/plugins

[auth]
disable_login_form = true
disable_signout_menu = true

[auth.anonymous]
enabled = true

'''.lstrip()
GRAFANA_PIDFILE = '/tmp/grafana.pid'
GRAFANA_PROCESS = None


# Use retries when proxying requests to the Grafana process,
# because it can take a moment for it to start listening.
requests = Session()
requests.mount('http://', HTTPAdapter(max_retries=Retry(
    connect=20,
    backoff_factor=0.1,
)))

dynamodb = boto3.client('dynamodb')


@contextmanager
def lock(context):
    """
    Lock the data so that only 1 Lambda function can read/write at a time.

    """

    while True:

        now = int(ceil(time()))
        seconds_remaining = int(ceil(
            context.get_remaining_time_in_millis() / 1000
        ))
        expire = now + seconds_remaining

        print('Acquiring DynamoDB lock')
        try:
            response = dynamodb.put_item(
                TableName=LOCK_TABLE_NAME,
                Item={
                    'Id': {
                        'S': LOCK_ID,
                    },
                    'Expire': {
                        'N': str(expire),
                    },
                },
                ConditionExpression='attribute_not_exists(Id) OR :Now > Expire',
                ExpressionAttributeValues={
                    ':Now': {
                        'N': str(now),
                    },
                },
            )
        except ClientError as error:
            code = error.response['Error']['Code']
            if code == 'ConditionalCheckFailedException':
                print('Waiting for lock')
                sleep(0.1)
            elif code == 'ProvisionedThroughputExceededException':
                print('Waiting for throttle')
                sleep(0.2)
            else:
                raise
        else:
            if response['ResponseMetadata']['HTTPStatusCode'] != 200:
                raise Exception('ERROR: {}'.format(response))
            else:
                break

    try:
        yield
    finally:

        attempts = 5
        while True:

            print('Releasing DynamoDB lock')
            try:
                response = dynamodb.delete_item(
                    TableName=LOCK_TABLE_NAME,
                    Key={
                        'Id': {
                            'S': LOCK_ID,
                        },
                    },
                )
            except ClientError as error:
                code = error.response['Error']['Code']
                if code == 'ProvisionedThroughputExceededException':
                    print('Waiting for throttle')
                    sleep(0.2)
                else:
                    raise
            else:
                if response['ResponseMetadata']['HTTPStatusCode'] != 200:
                    if attempts:
                        print('WARNING: {}'.format(response))
                        attempts -= 1
                        sleep(0.2)
                    else:
                        raise Exception('ERROR: {}'.format(response))
                else:
                    break


def proxy_request(path, event):

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
    headers.pop('content-length', None)
    headers.pop('transfer-encoding', None)

    print(headers, 'isBase64Encoded:', is_binary)

    return {
        'body': body,
        'headers': dict(headers),
        'statusCode': response.status_code,
        'isBase64Encoded': is_binary,
    }


def start_grafana(event):
    """
    Configures Grafana and then starts it, unless it is already running.

    """

    global GRAFANA_PROCESS

    if GRAFANA_PROCESS and not GRAFANA_PROCESS.poll():
        print('Grafana is already running')
        return

    with open(GRAFANA_CONFIG, 'wt') as config_file:
        config_file.write(GRAFANA_CONFIG_TEMPLATE.format(
            domain=event['headers']['Host'],
            stage=event['requestContext']['stage'],
        ))

    print('Starting Grafana')
    GRAFANA_PROCESS = Popen((
        GRAFANA_BIN,
        '-homepath', GRAFANA_HOME,
        '-config', GRAFANA_CONFIG,
        '-pidfile', GRAFANA_PIDFILE,
    ))


def stop_grafana():
    """
    Stops Grafana if it is running.

    """

    global GRAFANA_PROCESS

    if GRAFANA_PROCESS:
        print('Stopping Grafana')
        GRAFANA_PROCESS.terminate()
        GRAFANA_PROCESS.wait(timeout=5)
        GRAFANA_PROCESS = None


def sync_data(download=False, upload=False):

    if download:
        print('todo: dynamodb: get data versions/hashes')
        print('todo: s3: download changed data')

    if upload:
        print('todo: s3: upload changed data')
        import subprocess
        subprocess.check_call(('find', '/tmp/'))


def lambda_handler(event, context):

    print(event)

    if not os.path.exists(GRAFANA_HOME):
        print('todo: run function {}'.format(LAMBDA_BUILD_FUNCTION_NAME))
        raise NotImplementedError('todo: trigger build lambda, return error')

    path = PATH_PREFIX_RE.sub('', event['path'])

    if path.startswith('/public/'):

        # Static media does not require a data sync, so bypass the lock
        # and reuse the running Grafana process if there is one.

        start_grafana(event)
        response = proxy_request(path, event)

    else:

        # Regular paths might change the state on disk, including the SQLite
        # database, so use a lock and sync data for the request.

        stop_grafana()

        with lock(context):
            sync_data(download=True)
            start_grafana(event)
            response = proxy_request(path, event)
            stop_grafana()
            sync_data(upload=True)

    return response
