resource "random_id" "name" {
  prefix      = "raymondbutcher-grafana-lambda-"
  byte_length = 4
}

module "grafana" {
  source = "../"
  name   = "${random_id.name.hex}"
}
