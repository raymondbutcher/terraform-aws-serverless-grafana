variable "name" {
  type = "string"
}

variable "enable_api_gateway_cloudwatch_role" {
  default = false
}

variable "enable_api_gateway_logs" {
  default = false
}

variable "memory_size" {
  description = "Amount of memory in MB your Lambda Function can use at runtime"
  type        = "string"
  default     = 512
}

variable "timeout" {
  description = "The amount of time your Lambda Function has to run in seconds (allow an extra 20-60 seconds for install time)"
  type        = "string"
  default     = 180
}
