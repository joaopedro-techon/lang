data "aws_caller_identity" "current" {}

data "aws_secretsmanager_secret_version" "kafka_kcert" {
  secret_id = "{{SECRET_NAME}}"
}
