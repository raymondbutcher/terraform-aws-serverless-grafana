resource "aws_api_gateway_account" "global" {
  count               = "${var.enable_api_gateway_cloudwatch_role ? 1 : 0}"
  cloudwatch_role_arn = "${join("", aws_iam_role.api_gateway_cloudwatch.*.arn)}"
}

resource "aws_api_gateway_rest_api" "grafana" {
  name               = "${var.name}"
  binary_media_types = ["*/*", "/"]  # todo: check if needed
}

resource "null_resource" "binary_support" {
  triggers {
    rest_api_id = "${aws_api_gateway_rest_api.grafana.id}"
  }

  provisioner "local-exec" {
    command = "aws apigateway update-rest-api --rest-api-id ${aws_api_gateway_rest_api.grafana.id} --patch-operations 'op=add,path=/binaryMediaTypes/*~1*'"
  }
}

resource "aws_api_gateway_resource" "grafana" {
  rest_api_id = "${aws_api_gateway_rest_api.grafana.id}"
  parent_id   = "${aws_api_gateway_rest_api.grafana.root_resource_id}"
  path_part   = "{proxy+}"
}

resource "aws_api_gateway_method" "grafana" {
  rest_api_id   = "${aws_api_gateway_rest_api.grafana.id}"
  resource_id   = "${aws_api_gateway_resource.grafana.id}"
  http_method   = "ANY"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "grafana" {
  rest_api_id             = "${aws_api_gateway_rest_api.grafana.id}"
  resource_id             = "${aws_api_gateway_resource.grafana.id}"
  http_method             = "${aws_api_gateway_method.grafana.http_method}"
  type                    = "AWS_PROXY"
  uri                     = "arn:aws:apigateway:${local.region}:lambda:path/2015-03-31/functions/${aws_lambda_function.lambda_run.arn}/invocations"
  integration_http_method = "POST"
}

resource "aws_api_gateway_integration_response" "grafana" {
  depends_on = [
    "aws_api_gateway_integration.grafana",
  ]

  rest_api_id = "${aws_api_gateway_rest_api.grafana.id}"
  resource_id = "${aws_api_gateway_resource.grafana.id}"
  http_method = "${aws_api_gateway_method.grafana.http_method}"
  status_code = "200"
}

resource "aws_api_gateway_method_response" "grafana" {
  rest_api_id = "${aws_api_gateway_rest_api.grafana.id}"
  resource_id = "${aws_api_gateway_resource.grafana.id}"
  http_method = "${aws_api_gateway_method.grafana.http_method}"
  status_code = "200"
}

resource "aws_api_gateway_deployment" "grafana" {
  depends_on = [
    "aws_api_gateway_method.grafana",
    "aws_api_gateway_integration.grafana",
    "null_resource.binary_support",
  ]

  rest_api_id = "${aws_api_gateway_rest_api.grafana.id}"
  stage_name  = "test1"                                  # todo: choose name
}

resource "aws_api_gateway_method_settings" "grafana" {
  rest_api_id = "${aws_api_gateway_rest_api.grafana.id}"
  stage_name  = "${aws_api_gateway_deployment.grafana.stage_name}"
  method_path = "*/*"

  settings {
    logging_level = "INFO"
  }

  depends_on = ["aws_iam_role_policy.api_gateway_cloudwatch"]
}

resource "aws_lambda_permission" "grafana" {
  statement_id  = "AllowExecutionFromAPIGateway"
  action        = "lambda:InvokeFunction"
  function_name = "${aws_lambda_function.lambda_run.arn}"
  principal     = "apigateway.amazonaws.com"
  source_arn    = "arn:aws:execute-api:${local.region}:${local.account_id}:${aws_api_gateway_rest_api.grafana.id}/*"
}
