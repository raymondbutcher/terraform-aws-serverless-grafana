module "lambda" {
  source = "git@github.com:claranet/terraform-aws-lambda.git?ref=ray/fix-splat"

  function_name = "${var.name}"
  description   = "Grafana"
  handler       = "lambda.lambda_handler"
  memory_size   = 512
  runtime       = "python3.6"
  timeout       = "${var.timeout}"

  source_path = "${path.module}/lambda"
}
