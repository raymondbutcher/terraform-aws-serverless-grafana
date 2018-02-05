import boto3
import os
import shutil
import subprocess
import tempfile
import zipfile

from botocore.exceptions import ClientError
from botocore.vendored import requests


BUCKET = os.environ['BUCKET']

BUILD_DIR = '/tmp/lambda'
BUILD_ZIP = '/tmp/lambda.zip'

LAMBDA_FUNCTION_NAME = os.environ['LAMBDA_FUNCTION_NAME']
LAMBDA_SOURCE_KEY = os.environ['LAMBDA_SOURCE_KEY']
LAMBDA_SOURCE_NAME = os.path.basename(LAMBDA_SOURCE_KEY)
LAMBDA_SOURCE_PATH = '/tmp/' + LAMBDA_SOURCE_NAME
LAMBDA_ZIP_KEY = os.environ['LAMBDA_ZIP_KEY']

GRAFANA_DOWNLOAD_URL = os.environ['GRAFANA_DOWNLOAD_URL']
GRAFANA_DOWNLOAD_PATH = '/tmp/grafana.tar.gz'
GRAFANA_EXTRACT_DIR = '/tmp/grafana'

aws_lambda = boto3.client('lambda')
s3 = boto3.client('s3')


def http_download(url, dest):
    print('Downloading {}'.format(url))
    _, temp_path = tempfile.mkstemp()
    with open(temp_path, 'wb') as temp_file:
        response = requests.get(url, stream=True)
        shutil.copyfileobj(response.raw, temp_file)
    os.rename(temp_path, dest)


def s3_download(bucket, key, dest, allow_missing=False):
    print('Downloading s3://{}/{}'.format(bucket, key))
    _, temp_path = tempfile.mkstemp()
    try:
        s3.download_file(bucket, key, temp_path)
    except ClientError:
        if allow_missing:
            print('Could not download from s3://{}/{}'.format(bucket, key))
        else:
            raise
    else:
        os.rename(temp_path, dest)


def s3_upload(path, bucket, key):
    print('Uploading s3://{}/{}'.format(bucket, key))
    with open(path, 'rb') as open_file:
        response = s3.put_object(
            Bucket=bucket,
            Key=key,
            Body=open_file,
        )
    if response['ResponseMetadata']['HTTPStatusCode'] != 200:
        raise Exception('ERROR: {}'.format(response))
    return response


def lambda_handler(event, context):

    for path in (BUILD_DIR, GRAFANA_EXTRACT_DIR):
        if os.path.exists(path):
            print('Cleaning up {}'.format(path))
            shutil.rmtree(path)

    download_cache_key = 'grafana/' + os.path.basename(GRAFANA_DOWNLOAD_URL)

    if not os.path.exists(GRAFANA_DOWNLOAD_PATH):
        s3_download(
            bucket=BUCKET,
            key=download_cache_key,
            dest=GRAFANA_DOWNLOAD_PATH,
            allow_missing=True,
        )

    if not os.path.exists(GRAFANA_DOWNLOAD_PATH):
        http_download(GRAFANA_DOWNLOAD_URL, GRAFANA_DOWNLOAD_PATH)
        s3_upload(GRAFANA_DOWNLOAD_PATH, BUCKET, download_cache_key)

    s3_download(
        bucket=BUCKET,
        key=LAMBDA_SOURCE_KEY,
        dest=LAMBDA_SOURCE_PATH,
    )

    print('Extracting {}'.format(GRAFANA_DOWNLOAD_PATH))
    os.mkdir(GRAFANA_EXTRACT_DIR)
    subprocess.check_call((
        'tar',
        '-xf', GRAFANA_DOWNLOAD_PATH,
        '-C', GRAFANA_EXTRACT_DIR,
        '--strip', '1',
    ))

    print('Building {}'.format(BUILD_DIR))
    os.mkdir(BUILD_DIR)
    os.rename(LAMBDA_SOURCE_PATH, os.path.join(BUILD_DIR, LAMBDA_SOURCE_NAME))
    os.rename(GRAFANA_EXTRACT_DIR, os.path.join(BUILD_DIR, 'grafana'))

    print('Zipping {}'.format(BUILD_DIR))
    _, temp_path = tempfile.mkstemp()
    with zipfile.ZipFile(temp_path, 'w') as zip_file:
        for root, sub_dirs, files in os.walk(BUILD_DIR):
            for file_name in files:
                absolute_path = os.path.join(root, file_name)
                relative_path = os.path.relpath(absolute_path, BUILD_DIR)
                try:
                    zip_file.write(absolute_path, relative_path)
                except Exception as error:
                    print('ERROR: {}'.format(error))
                    raise
                
    os.rename(temp_path, BUILD_ZIP)

    response = s3_upload(BUILD_ZIP, BUCKET, LAMBDA_ZIP_KEY)
    version = response['VersionId']

    print('Updating Lambda Function {}'.format(LAMBDA_FUNCTION_NAME))
    response = aws_lambda.update_function_code(
        FunctionName=LAMBDA_FUNCTION_NAME,
        S3Bucket=BUCKET,
        S3Key=LAMBDA_ZIP_KEY,
        S3ObjectVersion=version,
    )
    if response['ResponseMetadata']['HTTPStatusCode'] != 200:
        raise Exception('ERROR: {}'.format(response))
