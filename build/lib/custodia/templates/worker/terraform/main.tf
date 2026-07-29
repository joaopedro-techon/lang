module "ecs-worker-task" {
  source = "git::https://github.com/itau-corp/itau-hn8-modules-ecs-service.git//modules/worker?ref=v0.51.2"

  ############# definições basicas do service
  environment                        = var.environment
  ecs_cluster_name                   = var.ecs_cluster_name
  feature_name                       = local.feature_name
  microservice_name                  = local.microservice_name
  service_desired_count              = var.service_desired_count
  service_deployment_maximum_percent = var.service_deployment_maximum_percent
  service_launch_config              = var.service_launch_config
  task_runtime_platform              = local.task_runtime_platform

  ############# configurações minimas de rede
  service_vpc_id      = var.service_vpc_id
  service_cidr_blocks = var.service_cidr_blocks
  service_subnets     = var.service_subnets
  task_container_port = var.task_container_port
  task_health_check   = local.task_health_check

  ############# definições basicas do container
  task_cpu                           = var.task_cpu
  task_memory                        = var.task_memory
  task_ulimits_vars                  = var.task_ulimits_vars
  task_log_driver                    = var.task_log_driver
  task_ephemeral_storage_size_in_gib = var.task_ephemeral_storage_size_in_gib
  task_environment_vars              = local.task_environment_vars
  task_secrets_vars                  = local.task_secrets_vars
  task_datadog                       = local.task_datadog
  task_custom_image                  = local.task_custom_image

  ############# tags obrigatorias
  sigla               = local.sigla
  produto             = local.produto
  context             = local.context
  owner_contact_email = local.owner_contact_email
  tech_team_email     = local.tech_team_email
  finalidade          = local.finalidade
  squad               = local.squad
  github_repo_id      = var.github_repo_id
  github_repo_name    = var.github_repo_name
  build_version       = var.iupipes_build_version
  additional_tags     = local.additional_tags

  ############# roles
  task_role_arn           = module.iamsr_module.roles[1].arn
  task_execution_role_arn = module.iamsr_module.roles[1].arn

  ############# Para configurações complementares, consulte: https://github.com/itau-corp/itau-hn8-modules-ecs-service/

  depends_on = [
    module.iamsr_module.roles
  ]

  #########################################
  #### Autoscaling por profundidade de fila SQS
  #########################################

  autoscaling = {
    enabled      = true
    min_capacity = var.autoscaling.min_capacity
    max_capacity = var.autoscaling.max_capacity
    sqs = {
      enabled = true
      scale_up = {
        cooldown           = var.autoscaling.scale_up.cooldown
        evaluation_periods = var.autoscaling.scale_up.evaluation_periods
        threshold          = var.autoscaling.scale_up.threshold
        steps              = var.autoscaling.scale_up.steps
      }
      scale_down = {
        cooldown           = var.autoscaling.scale_down.cooldown
        evaluation_periods = var.autoscaling.scale_down.evaluation_periods
        threshold          = var.autoscaling.scale_down.threshold
        steps              = var.autoscaling.scale_down.steps
      }
      queue_names = var.autoscaling.queue_names
    }
  }
}
