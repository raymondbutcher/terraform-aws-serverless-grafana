import boto3
import json
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


FILES_BUCKET = os.environ['FILES_BUCKET']
FILES_PREFIX = os.environ['FILES_PREFIX']
FILES_TABLE = os.environ['FILES_TABLE']
FILES_ID = '1'
LOCK_TABLE = os.environ['LOCK_TABLE']
LOCK_ID = '1'

PATH_PREFIX_RE = re.compile('^/grafana')

GRAFANA_HOME = os.path.join(os.path.dirname(__file__), 'grafana')
GRAFANA_BIN = os.path.join(GRAFANA_HOME, 'bin', 'grafana-server')
GRAFANA_DATA = '/tmp/grafana/data'
GRAFANA_PLUGINS = '/tmp/grafana/plugins'
GRAFANA_CONFIG = '/tmp/grafana.conf'
GRAFANA_CONFIG_TEMPLATE = '''
[server]
domain = {domain}
root_url = %(protocol)s://%(domain)s:/{stage}/grafana

[paths]
data = {data}
logs = /tmp/grafana/logs
plugins = {plugins}
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
s3 = boto3.client('s3')


@contextmanager
def dynamodb_lock(context):
    """
    Lock the data so that only 1 Lambda function can read/write at a time.

    """

    dynamodb_lock_acquire(context)
    try:
        yield
    finally:
        dynamodb_lock_release()


def dynamodb_lock_acquire(context):
    """
    Acquires the DynamoDB lock.

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
                TableName=LOCK_TABLE,
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


def dynamodb_lock_release():
    """
    Releases the DynamoDB lock.

    """

    attempts = 5
    while True:

        print('Releasing DynamoDB lock')
        try:
            response = dynamodb.delete_item(
                TableName=LOCK_TABLE,
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


def dynamodb_get_files():
    """
    Gets file data.

    """

    while True:

        print('Getting file data')
        try:
            response = dynamodb.get_item(
                TableName=FILES_TABLE,
                Key={
                    'Id': {
                        'S': FILES_ID,
                    }
                },
                ConsistentRead=True,
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
                raise Exception('ERROR: {}'.format(response))
            else:
                item = response.get('Item')
                if item:
                    return json.loads(item['Files']['S'])
                else:
                    print('No file data found!')
                    return {}


def dynamodb_put_files(files):
    """
    Stores file data.

    """

    files_json = json.dumps(files)

    while True:

        try:
            response = dynamodb.put_item(
                TableName=FILES_TABLE,
                Item={
                    'Id': {
                        'S': FILES_ID,
                    },
                    'Files': {
                        'S': files_json,
                    },
                }
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

    headers = response.headers
    headers.pop('content-length', None)
    headers.pop('transfer-encoding', None)

    if response.encoding:
        body = response.text
        is_binary = False
        print('Text response:', headers)
    else:
        body = b64encode(response.content).decode('utf-8')
        is_binary = True
        print('Base 64 encoded response:', headers)

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
            data=GRAFANA_DATA,
            plugins=GRAFANA_PLUGINS,
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


def sync_data(download=False, upload=False, _versions={}, _times={}):

    if download:

        files = dynamodb_get_files()

        created_dirs = set()

        for relative_path, details in files.items():

            file_version, file_time = details

            absolute_path = '/tmp/grafana/' + relative_path
            dir_path = os.path.dirname(absolute_path)

            if _versions.get(relative_path) == file_version:

                print('Already have {}'.format(relative_path))
                created_dirs.add(dir_path)

            else:

                print('Downloading {}'.format(relative_path))

                if dir_path not in created_dirs:
                    os.makedirs(dir_path, exist_ok=True)
                    created_dirs.add(dir_path)

                s3.download_file(
                    Bucket=FILES_BUCKET,
                    Key=FILES_PREFIX + '/' + relative_path,
                    Filename=absolute_path,
                    ExtraArgs={
                        'VersionId': file_version,
                    },
                )

                _versions[relative_path] = file_version
                _times[relative_path] = os.stat(absolute_path).st_mtime_ns

    if upload:

        for grafana_path in (GRAFANA_DATA, GRAFANA_PLUGINS):
            for root, sub_dirs, files in os.walk(grafana_path):
                for file_name in files:

                    absolute_path = os.path.join(root, file_name)
                    relative_path = os.path.relpath(
                        absolute_path, '/tmp/grafana'
                    )

                    file_time = os.stat(absolute_path).st_mtime_ns

                    if file_time == _times.get(relative_path):
                        print('Unchanged', relative_path)
                    else:

                        print('Uploading {}'.format(relative_path))
                        with open(absolute_path, 'rb') as open_file:
                            response = s3.put_object(
                                Body=open_file,
                                Bucket=FILES_BUCKET,
                                Key=FILES_PREFIX + '/' + relative_path,
                            )
                        if response['ResponseMetadata']['HTTPStatusCode'] != 200:
                            raise Exception('ERROR: {}'.format(response))

                        _versions[relative_path] = response['VersionId']
                        _times[relative_path] = file_time

        files = {}
        for key in _versions:
            files[key] = [_versions[key], _times[key]]

        dynamodb_put_files(files)


def lambda_handler(event, context):

    print('Request:', event)

    if not os.path.exists(GRAFANA_HOME):
        raise NotImplementedError('not built yet')

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

        with dynamodb_lock(context):
            sync_data(download=True)
            start_grafana(event)
            response = proxy_request(path, event)
            stop_grafana()
            sync_data(upload=True)

    return response
