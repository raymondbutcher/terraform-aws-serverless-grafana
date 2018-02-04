resource "aws_iam_role" "api_gateway_cloudwatch" {
  count = "${var.enable_api_gateway_cloudwatch_role ? 1 : 0}"

  name = "api-gateway-cloudwatch-logs"

  assume_role_policy = <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "",
      "Effect": "Allow",
      "Principal": {
        "Service": "apigateway.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
EOF
}

resource "aws_iam_role_policy" "api_gateway_cloudwatch" {
  count = "${var.enable_api_gateway_cloudwatch_role ? 1 : 0}"

  name = "${aws_iam_role.api_gateway_cloudwatch.name}"
  role = "${join("", aws_iam_role.api_gateway_cloudwatch.*.id)}"

  policy = <<EOF
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "logs:CreateLogGroup",
                "logs:CreateLogStream",
                "logs:DescribeLogGroups",
                "logs:DescribeLogStreams",
                "logs:PutLogEvents",
                "logs:GetLogEvents",
                "logs:FilterLogEvents"
            ],
            "Resource": "*"
        }
    ]
}
EOF
}
