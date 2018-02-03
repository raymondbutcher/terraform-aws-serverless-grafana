from data import lock, download_data, upload_data
from install import install_grafana
from process import start_grafana, stop_grafana
from proxy import proxy_request


def lambda_handler(event, context):

    # Install Grafana to the /tmp directory if it's not already there.
    # This takes about 15 seconds the first time, but subsequent requests
    # will reuse it .
    install_grafana()

    # Lock the data so that only 1 Lambda function can read/write at a time.
    seconds_remaining = int(context.get_remaining_time_in_millis() / 1000)
    with lock(seconds_remaining + 10):

        # Download Grafana's data files from S3.
        download_data()

        # Start the Grafana process in the background.
        process = start_grafana()

        # Pass along the HTTP request to Grafana and get the response.
        response = proxy_request(event)

        # Stop Grafana gracefully.
        stop_grafana(process)

        # Upload any changed data to S3.
        upload_data()

    # Return the response from Grafana to the client.
    return response
