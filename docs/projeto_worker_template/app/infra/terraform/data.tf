data "aws_caller_identity" "current" {}

data "aws_region" "current" {}

data "aws_secretsmanager_secret" "client_secrets" {
  name = "/Produto/Credentials/Microservice" // [PARAMETRO_IA - Deve perguntar o nome do Secret das Credenciais STS da aplicação]
}
