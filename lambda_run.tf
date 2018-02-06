resource "aws_lambda_function" "lambda_run" {
  function_name = "${var.name}"
  description   = "Serverless Grafana"
  role          = "${aws_iam_role.lambda_run.arn}"
  handler       = "lambda_run.lambda_handler"
  memory_size   = 512
  runtime       = "python3.6"
  timeout       = 60
  s3_bucket     = "${aws_s3_bucket_object.lambda_run_zip.bucket}"
  s3_key        = "${aws_s3_bucket_object.lambda_run_zip.key}"

  environment {
    variables {
      LAMBDA_BUILD_FUNCTION_NAME = "${module.lambda_build.function_name}"
      LOCK_TABLE_NAME            = "${aws_dynamodb_table.lock.id}"
    }
  }
}

# Create the role.

data "aws_iam_policy_document" "lambda_run_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda_run" {
  name               = "${var.name}"
  assume_role_policy = "${data.aws_iam_policy_document.lambda_run_assume_role.json}"
}

data "aws_iam_policy_document" "lambda_run" {
  # Logs

  statement {
    effect = "Allow"

    actions = [
      "logs:CreateLogGroup",
    ]

    resources = [
      "arn:aws:logs:${local.region}:${local.account_id}:*",
    ]
  }

  statement {
    effect = "Allow"

    actions = [
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]

    resources = [
      "arn:aws:logs:${local.region}:${local.account_id}:log-group:/aws/lambda/${aws_lambda_function.lambda_run.function_name}:*",
    ]
  }

  # S3 bucket

  statement {
    effect = "Allow"

    actions = [
      "s3:GetObject*",
      "s3:PutObject",
    ]

    resources = [
      "${aws_s3_bucket.bucket.arn}/*",
    ]
  }

  # DynamoDB lock table

  statement {
    effect = "Allow"

    actions = [
      "dynamodb:PutItem",
      "dynamodb:DeleteItem",
    ]

    resources = [
      "${aws_dynamodb_table.lock.arn}",
    ]
  }
}

resource "aws_iam_policy" "lambda_run" {
  name   = "${var.name}"
  policy = "${data.aws_iam_policy_document.lambda_run.json}"
}

resource "aws_iam_policy_attachment" "lambda_run" {
  name       = "${var.name}"
  roles      = ["${aws_iam_role.lambda_run.name}"]
  policy_arn = "${aws_iam_policy.lambda_run.arn}"
}
