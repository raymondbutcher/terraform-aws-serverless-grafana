import re

from base64 import b64decode, b64encode

from botocore.vendored.requests import Session
from botocore.vendored.requests.adapters import HTTPAdapter
from botocore.vendored.requests.packages.urllib3.util.retry import Retry


URL_PREFIX_RE = re.compile('^/grafana')


# Use retries when proxying requests to the Grafana process,
# because it can take a moment for it to start listening.
grafana_session = Session()
grafana_session.mount('http://', HTTPAdapter(max_retries=Retry(
    connect=20,
    backoff_factor=0.1,
)))


def proxy_request(event):

    url = 'http://127.0.0.1:3000' + URL_PREFIX_RE.sub('', event['path'])

    if event['isBase64Encoded']:
        request_body = b64decode(event['body'])
    else:
        request_body = None

    response = grafana_session.request(
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
