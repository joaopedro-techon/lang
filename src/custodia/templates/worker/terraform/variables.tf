############## definições basicas do service
variable "environment" {
  type = string
}

variable "ecs_cluster_name" {
  type = string
}

variable "service_desired_count" {
  type    = number
  default = 1
}

variable "service_deployment_maximum_percent" {
  type    = number
  default = 200
}

variable "service_launch_config" {
  type = object({
    launch_type = string
    capacity_providers = optional(list(object({
      capacity_provider = string
      base              = number
      weight            = number
      upper_case        = optional(bool, true)
    })), [])
  })
  validation {
    condition     = contains(["EC2", "FARGATE"], upper(var.service_launch_config.launch_type))
    error_message = "A variavel 'service_launch_config.launch_type' deve estar preenchida corretamente ('EC2' ou 'FARGATE')."
  }
}

############## configurações minimas de rede
variable "service_vpc_id" {
  type = string
  validation {
    condition     = can(regex("^(vpc-[0-9a-z-]+)$", var.service_vpc_id))
    error_message = "Erro ao configurar 'service_vpc_id' os valores devem estar configurada corretamente, começando com \"vpc-*\"."
  }
}

variable "service_cidr_blocks" {
  type    = list(string)
  default = ["0.0.0.0/0"]
  validation {
    condition     = alltrue([for cidr in var.service_cidr_blocks : can(regex("^(([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\\.){3}([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])(\\/(3[0-2]|[1-2][0-9]|[0-9]))$", cidr))])
    error_message = "Erro ao configurar 'service_cidr_blocks' os valores devem estar configurada corretamente. Ex. 84.240.40.0/24"
  }
}

variable "service_subnets" {
  type = list(string)
  validation {
    condition     = alltrue([for subnet in var.service_subnets : can(regex("^subnet-[0-9a-z-]+$", subnet))])
    error_message = "Erro ao configurar 'service_subnets' os valores devem estar configurada corretamente, começando com \"subnet-\"."
  }
}

variable "task_container_port" {
  type = list(object({
    containerPort = number
    hostPort      = optional(number, null)
    protocol      = optional(string, "tcp")
  }))
  default = [{
    containerPort = 2000
  }]
}

############## definições basicas do container
variable "task_cpu" {
  type    = number
  default = 512
}

variable "task_memory" {
  type    = number
  default = 1024
}

variable "task_ulimits_vars" {
  type = list(object({
    name      = string
    softLimit = number
    hardLimit = number
  }))
  default = []
}

variable "task_log_driver" {
  type = object({
    log-driver                        = string
    cloudwatch-retention-logs-in-days = optional(number, 7)     # Deprecated será removido na proxima release
    splunk-format                     = optional(string, "raw") # Deprecated será removido na proxima release
    splunk-index                      = optional(string, "")    # Deprecated será removido na proxima release
    splunk-token                      = optional(string, "")    # Deprecated será removido na proxima release
    tag                               = optional(string, " ")   # Deprecated será removido na proxima release
    options                           = optional(map(any), {})
    secret-options                    = optional(map(any), {})
  })
  validation {
    condition     = contains(["awslogs", "splunk", "awsfirelens"], lower(var.task_log_driver.log-driver))
    error_message = "A variavel 'task_log_driver.log-driver' deve estar preenchida corretamente. Verifique e tente novamente."
  }
  validation {
    condition     = can(regex("^(|ssm:.+|arn:aws:secretsmanager:.+:[0-9]{12}:secret:.+)$", var.task_log_driver.splunk-token))
    error_message = "A variavel 'task_log_driver.splunk-token' deve estar preenchida corretamente. Verifique e tente novamente."
  }
}

variable "task_ephemeral_storage_size_in_gib" {
  description = <<-EOT
    Tamanho do storage efemero (GiB) da task.
    0 (default/FinOps): nao declara o bloco ephemeralStorage e a task usa os 20 GiB gratuitos da AWS no Fargate.
    Override: defina um valor entre 21 e 200 no terraform.tfvars apenas quando a workload realmente precisar de disco adicional.
  EOT
  type        = number
  default     = 0
}

############## tags obrigatorias
variable "github_repo_name" {
  type    = string
  default = "GITHUB_REPOSITORY_TAG_PLACEHOLDER"
}

variable "github_repo_id" {
  type    = string
  default = "GITHUB_REPOSITORY_TAG_PLACEHOLDER"
}

variable "iupipes_build_version" {
  type    = string
  default = "GITHUB_REPOSITORY_TAG_PLACEHOLDER"
}

variable "sts_internal_url" {
  type = string
}

variable "sts_external_url" {
  type = string
}

variable "autoscaling" {
  type = object({
    min_capacity = number
    max_capacity = number
    scale_up = object({
      threshold          = number
      cooldown           = number
      evaluation_periods = number
      steps = optional(
        list(object({
          lower_bound        = optional(number, null)
          upper_bound        = number
          scaling_adjustment = number
        })),
        [{ upper_bound = 0, scaling_adjustment = 1 }]
      )
    })
    scale_down = object({
      threshold          = number
      cooldown           = number
      evaluation_periods = number
      steps = optional(
        list(object({
          lower_bound        = optional(number, null)
          upper_bound        = number
          scaling_adjustment = number
        })),
        [{ upper_bound = 0, scaling_adjustment = -1 }]
      )
    })
    queue_names = list(string)
  })
}
