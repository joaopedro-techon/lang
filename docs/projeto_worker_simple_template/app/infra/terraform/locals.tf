locals {

  sigla = "XXX"

  sigla_app = "XXX-XXXXX"

  produto = "Nome do produto"

  context = "context"

  owner_contact_email = "owner-contact-email@itau-unibanco.com.br"

  tech_team_email = "tech-team-email@itau-unibanco.com.br"

  finalidade = "modernizacao"

  squad = "squad"

  feature_name = "feature"

  microservice_name = "microservice"

  additional_tags = {
    "sigla-app"                          = local.sigla_app
    "iu:finops:alocacao:squad"           = "SQUAD (S000000)"
    "iu:finops:alocacao:sigla"           = lower(local.sigla)
    "iu:finops:alocacao:sigla-app"       = local.sigla_app
    "iu:finops:alocacao:produto"         = "Nome-do-produto"
    "iu:finops:alocacao:empresa"         = "341"
    "iu:finops:alocacao:projeto"         = "projeto"
    "iu:finops:alocacao:oferta"          = "Oferta"
    "iu:finops:alocacao:servico-negocio" = "Servico de negocio"
    "MicroServiceName"                   = local.microservice_name
    "tech-team-email"                    = local.tech_team_email
    "owner-team-email"                   = local.owner_contact_email
  }

  default_container_port = (
    var.task_container_port[0].hostPort == null
    ? var.task_container_port[0].containerPort
    : var.task_container_port[0].hostPort
  )

  task_environment_vars = [
    {
      name  = "ENVIRONMENT"
      value = var.environment
    },
    # Deriva a porta da aplicacao do proprio containerPort. Sem isso, server.port
    # (application.yml) e task_container_port sao dois numeros independentes que
    # so' coincidem por convencao — e quando divergem, o health check bate numa
    # porta onde ninguem escuta e a task nunca fica healthy.
    {
      name  = "SERVER_PORT"
      value = local.default_container_port
    },
    {
      name  = "ECS_FARGATE"
      value = "true"
    },
    {
      name  = "INITIAL_RAM_PERCENTAGE"
      value = 35
    },
    {
      name  = "MAX_RAM_PERCENTAGE"
      value = 75
    },
    {
      name  = "JAVA_TOOL_OPTIONS"
      value = "-Dlog.console.active=true"
    },
    {
      name  = "STS_INTERNAL_URL"
      value = var.sts_internal_url
    },
    {
      name  = "STS_EXTERNAL_URL"
      value = var.sts_external_url
    },
    {
      name  = "AWS_ACCOUNT_ID"
      value = data.aws_caller_identity.current.account_id
    },
    # ARN completo, e não o nome do tópico — ver sns.tf.
    {
      name  = "SNS_PEDIDO_TOPIC_ARN"
      value = aws_sns_topic.pedido.arn
    }
  ]


  task_secrets_vars = [
    {
      name      = "APP_CLIENT_ID"
      valueFrom = "${data.aws_secretsmanager_secret.client_secrets.arn}:client_id::"
    },
    {
      name      = "APP_CLIENT_SECRET"
      valueFrom = "${data.aws_secretsmanager_secret.client_secrets.arn}:client_secret::"
    }
  ]

  task_runtime_platform = {
    operatingSystemFamily = "LINUX"
    cpuArchitecture       = "ARM64"
  }

  # Readiness, não o /health agregado: durante o warm-up o agregado responde DOWN e o ECS
  # entende container morto, reiniciando em loop antes de a aplicação chegar a subir.
  healthcheck_path = "/actuator/health/readiness"

  task_health_check = {
    interval    = 30
    timeout     = 10
    startPeriod = 120
    retries     = 5
    command = [
      "CMD-SHELL", "curl -f http://localhost:${local.default_container_port}${local.healthcheck_path} || exit 1"
    ]
  }

  task_log_driver = {
    log-driver = "awsfirelens"
    options = {
      Name = "${local.sigla}-${local.feature_name}-${local.microservice_name}"
    }
  }

  task_datadog = {
    apm = {
      enabled          = true
      essential        = false
      ignore_resources = ["GET ${local.healthcheck_path}"]
    }

    log = {
      image            = "851725494844.dkr.ecr.sa-east-1.amazonaws.com/itau-corp-itau-ln6-container-fluent-bit-arm64:v0.0.4"
      enabled          = true
      essential        = true
      source           = "java"
      multiple_outputs = true
    }

    health_check = {
      enabled = true
      url     = "http://localhost:${local.default_container_port}${local.healthcheck_path}"
      tags = [
        "path:${local.healthcheck_path}"
      ]
    }

    additional_tags = {
      "sigla_app" = local.microservice_name
      "service"   = "${local.sigla}-${local.feature_name}-${local.microservice_name}"
    }

    org = "itau"

  }

  task_custom_image = "${data.aws_caller_identity.current.account_id}.dkr.ecr.${data.aws_region.current.name}.amazonaws.com/itau-${lower(local.sigla)}-app-${local.microservice_name}-${lower(var.environment)}"

}
