resource "random_id" "name" {
  prefix      = "raymondbutcher-grafana-lambda-"
  byte_length = 4
}

module "grafana" {
  source = "../"

  name = "${var.name}"

  enable_api_gateway_cloudwatch_role = "${var.enable_api_gateway_cloudwatch_role}"
  enable_api_gateway_logs            = "${var.enable_api_gateway_logs}"
}
