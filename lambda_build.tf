module "lambda_build" {
  source = "git@github.com:claranet/terraform-aws-lambda.git?ref=ray/fix-splat"

  function_name                  = "${var.name}-build"
  description                    = "Builds ${var.name}"
  handler                        = "lambda_build.lambda_handler"
  memory_size                    = 1024
  reserved_concurrent_executions = 1
  runtime                        = "python3.6"
  timeout                        = 300

  source_path = "${path.module}/lambda_build.py"

  attach_policy = true
  policy        = "${data.aws_iam_policy_document.lambda_build.json}"

  environment {
    variables {
      BUCKET               = "${aws_s3_bucket.bucket.bucket}"
      BUILD_KEY            = "${aws_s3_bucket_object.lambda_run_zip.key}"
      LAMBDA_FUNCTION_NAME = "${var.name}"
      LAMBDA_SOURCE_BUCKET = "${aws_s3_bucket_object.lambda_run_source.bucket}"
      LAMBDA_SOURCE_KEY    = "${aws_s3_bucket_object.lambda_run_source.key}"
      LAMBDA_ZIP_BUCKET    = "${aws_s3_bucket_object.lambda_run_zip.bucket}"
      LAMBDA_ZIP_KEY       = "${aws_s3_bucket_object.lambda_run_zip.key}"
      GRAFANA_DOWNLOAD_URL = "https://s3-us-west-2.amazonaws.com/grafana-releases/release/grafana-4.6.3.linux-x64.tar.gz"
    }
  }
}

data "aws_iam_policy_document" "lambda_build" {
  # Grant access to the bucket.
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

  # Grant access to update the run function.
  statement {
    effect = "Allow"

    actions = [
      "lambda:UpdateFunctionCode",
    ]

    resources = [
      "${aws_lambda_function.lambda_run.arn}",
    ]
  }
}

resource "null_resource" "trigger_build" {
  depends_on = [
    "aws_lambda_function.lambda_run",
    "aws_s3_bucket_object.lambda_run_source",
    "module.lambda_build",
  ]

  triggers {
    lambda_build = "${md5(file("${path.module}/lambda_build.py"))}"
    lambda_run   = "${md5(file("${path.module}/lambda_run.py"))}"
  }

  provisioner "local-exec" {
    command = "aws lambda invoke --function-name ${module.lambda_build.function_name} /dev/null" # todo: catch errors
  }
}
