resource "aws_dynamodb_table" "lock" {
  name           = "${var.name}-lock"
  read_capacity  = 2
  write_capacity = 2

  hash_key = "Id"

  attribute {
    name = "Id"
    type = "S"
  }
}

resource "aws_dynamodb_table" "files" {
  name           = "${var.name}-files"
  read_capacity  = 3
  write_capacity = 3

  hash_key = "Id"

  attribute {
    name = "Id"
    type = "S"
  }
}
