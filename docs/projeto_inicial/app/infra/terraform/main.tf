module "ecs-app-task" {
  source = "git::https://github.com/itau-corp/itau-hn8-modules-ecs-service.git//modules/app?ref=v0.51.1"

  ############# definições basicas do service
  environment                        = var.environment
  ecs_cluster_name                   = var.ecs_cluster_name
  feature_name                       = local.feature_name
  microservice_name                  = local.microservice_name
  service_desired_count              = var.service_desired_count
  service_deployment_maximum_percent = var.service_deployment_maximum_percent
  service_launch_config              = var.service_launch_config

  ############# configurações minimas de rede
  service_vpc_id         = var.service_vpc_id
  service_cidr_blocks    = var.service_cidr_blocks
  service_subnets        = var.service_subnets
  security_group_default = var.security_group_default
  task_container_port    = var.task_container_port
  task_health_check      = local.task_health_check
  tg_groups_config       = local.tg_groups_config
  lb_listeners_config    = local.lb_listeners_config

  ############# definições basicas do container
  task_cpu                           = var.task_cpu
  task_memory                        = var.task_memory
  task_ulimits_vars                  = var.task_ulimits_vars
  task_log_driver                    = var.task_log_driver
  task_ephemeral_storage_size_in_gib = var.task_ephemeral_storage_size_in_gib
  task_environment_vars              = local.task_environment_vars #opcional

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
}
