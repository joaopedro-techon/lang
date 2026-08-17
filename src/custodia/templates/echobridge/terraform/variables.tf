variable "sink_environment" {
  type = string
  validation {
    condition     = contains(["dev", "hom", "prod"], var.sink_environment)
    error_message = "A variavel 'sink_environment' deve estar preenchida corretamente, os valores permitidos sao 'dev', 'hom' e 'prod'. Verifique e tente novamente."
  }
}

variable "sink_ecs_cluster_name" {
  type = string
}

variable "sink_kafka_client_id" {
  type = string
}

variable "sink_kafka_group_id" {
  type = string
}

variable "sink_schema_topics" {
  type = list(object({
    bootstrap_servers = list(string)
    topics            = list(string)
    partitions        = list(number)
  }))
  default = []
}

variable "sink_schema_less_topics" {
  type = list(object({
    bootstrap_servers = list(string)
    topics            = list(string)
    partitions        = list(number)
  }))
  default = []
}

variable "sink_messaging_arn" {
  type    = string
  default = ""
  validation {
    condition     = can(regex("^(|arn:aws:(sqs|sns):.+:[0-9]{12}:.+)$", var.sink_messaging_arn))
    error_message = "A variavel 'sink_messaging_arn' deve estar preenchida corretamente usando o pattern de SQS ou SNS ARN"
  }
}

variable "sink_datadog_custom_config" {
  type = object({
    apm = object({
      cpu    = optional(number, 200)
      memory = optional(number, 512)
    }),
    log = object({
      cpu    = optional(number, 200)
      memory = optional(number, 512)
    })
  })
  default = {
    apm = {
      cpu    = 200
      memory = 512
    },
    log = {
      cpu    = 200
      memory = 512
    }
  }
}

variable "sink_rate_limit_enabled" {
  type    = bool
  default = false
}

variable "sink_rate_limit_standard_message_quotas" {
  type    = number
  default = 300
}

variable "sink_rate_limit_wait_timeout" {
  type    = string
  default = "5s"
}

variable "github_repo_id" {
  type    = string
  default = "{{GITHUB_REPO_ID}}"
}

variable "github_repo_name" {
  type    = string
  default = "{{GITHUB_REPO_NAME}}"
}

variable "sink_service_launch_config" {
  type = object({
    launch_type = string
    capacity_providers = optional(list(object({
      capacity_provider = string
      base              = number
      weight            = number
      upper_case        = optional(bool, false)
    })), [])
  })
  validation {
    condition     = contains(["EC2", "FARGATE"], upper(var.sink_service_launch_config.launch_type))
    error_message = "A variavel 'sink_service_launch_config.launch_type' deve estar preenchida corretamente ('EC2' ou 'FARGATE'). Verifique e tente novamente."
  }
}

variable "sink_service_vpc_id" {
  type = string
  validation {
    condition     = can(regex("^(vpc-[0-9a-z-]+)$", var.sink_service_vpc_id))
    error_message = "Erro ao configurar 'sink_service_vpc_id' os valores devem estar configurada corretamente, comecando com \"vpc-\"."
  }
}

variable "sink_service_cidr_blocks" {
  type    = list(string)
  default = ["0.0.0.0/0"]
  validation {
    condition     = alltrue([for cidr in var.sink_service_cidr_blocks : can(regex("^(([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\\.){3}([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])(/([0-9]|[1-2][0-9]|3[0-2]))?$", cidr))])
    error_message = "Erro ao configurar 'sink_service_cidr_blocks' os valores devem estar configurada corretamente. Ex. 84.240.40.0/24"
  }
}

variable "sink_service_subnets" {
  type = list(string)
  validation {
    condition     = alltrue([for subnet in var.sink_service_subnets : can(regex("^subnet-[0-9a-z-]+$", subnet))])
    error_message = "Erro ao configurar 'sink_service_subnets' os valores devem estar configurada corretamente, comecando com \"subnet-\"."
  }
}

variable "sink_security_group_default" {
  type = string
  validation {
    condition     = can(regex("^(sg-[0-9a-z-]+)$", var.sink_security_group_default))
    error_message = "Erro ao configurar a 'sink_security_group_default' os valores devem estar configurada corretamente, comecando com \"sg-\"."
  }
}

variable "sink_logging" {
  type = object({
    retention_in_days = optional(number, null)
    log_level         = optional(string, "INFO")
  })
  default = {
    retention_in_days = null
    log_level         = "INFO"
  }
  validation {
    condition     = contains(["INFO", "WARN", "ERROR"], var.sink_logging.log_level)
    error_message = "Valor invalido para sink_logging.log_level. Valores suportados INFO, WARN ou ERROR"
  }
}

variable "sink_output" {
  type = object({
    wrap_payload    = optional(bool, true)
    visible_headers = optional(bool, true)
  })
  default = {
    wrap_payload    = true
    visible_headers = true
  }
}

variable "sink_additional_tags" {
  type    = map(any)
  default = {}
}

variable "profile" {
  type    = string
  default = "MINIMUM_RESOURCE"
}
