from contextlib import contextmanager


@contextmanager
def lock(seconds):
    print('todo: dynamodb: acquire lock')
    yield
    print('todo: dynamodb: release lock')


def download_data():
    print('todo: dynamodb: get data versions/hashes')
    print('todo: s3: download changed data')


def upload_data():
    print('todo: s3: upload changed data')
