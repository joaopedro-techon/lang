data "aws_caller_identity" "current" {}

data "aws_region" "current" {}

data "aws_secretsmanager_secret" "client_secrets" {
  name = "{{SECRET_NAME}}"
}
