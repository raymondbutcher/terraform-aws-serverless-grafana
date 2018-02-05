resource "aws_s3_bucket" "bucket" {
  bucket        = "${var.name}"
  acl           = "private"
  force_destroy = true

  versioning {
    enabled = true
  }
}

resource "aws_s3_bucket_object" "lambda_run_source" {
  bucket  = "${aws_s3_bucket.bucket.id}"
  key     = "lambda_run.py"
  content = "${file("${path.module}/lambda_run.py")}"
  etag    = "${md5(file("${path.module}/lambda_run.py"))}"
}

data "archive_file" "lambda_run_zip" {
  type                    = "zip"
  source_content          = "${file("${path.module}/lambda_run.py")}"
  source_content_filename = "lambda_run.py"
  output_path             = "${path.module}/lambda_run.zip"
}

resource "aws_s3_bucket_object" "lambda_run_zip" {
  bucket  = "${aws_s3_bucket.bucket.id}"
  key     = "lambda_run.zip"
  content = "${file(data.archive_file.lambda_run_zip.output_path)}"

  lifecycle {
    ignore_changes = ["content"]
  }
}
