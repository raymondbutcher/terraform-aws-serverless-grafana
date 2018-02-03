from botocore.vendored.requests import Session
from botocore.vendored.requests.adapters import HTTPAdapter
from botocore.vendored.requests.packages.urllib3.util.retry import Retry


# Use retries when proxying requests to the Grafana process,
# because it can take a moment for it to start listening.
grafana_session = Session()
grafana_session.mount('http://', HTTPAdapter(max_retries=Retry(
    connect=20,
    backoff_factor=0.1,
)))


def proxy_request(event):

    print('todo: proxy api gateway request event to the grafana server')
    print(event)

    response = grafana_session.get('http://127.0.0.1:3000/')

    return {
        'body': response.content,
        'headers': response.headers,
        'status': response.status_code,
    }
