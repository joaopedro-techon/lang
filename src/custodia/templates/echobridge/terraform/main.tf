module "ecs-sink-connector" {
  # Verifique a versao latest / pre-release disponiveis:
  # https://github.com/itau-corp/itau-hn8-modules-ecs-echobridge
  source = "git::https://github.com/itau-corp/itau-hn8-modules-ecs-echobridge.git?ref={{MODULE_REF}}"

  ############## definicoes basicas do service
  sink_environment           = var.sink_environment
  sink_ecs_cluster_name      = var.sink_ecs_cluster_name
  sink_feature_name          = local.sink_feature_name
  sink_microservice_name     = local.sink_microservice_name
  sink_service_launch_config = var.sink_service_launch_config

  ############## configuracoes minimas de rede
  sink_service_vpc_id         = var.sink_service_vpc_id
  sink_service_cidr_blocks    = var.sink_service_cidr_blocks
  sink_service_subnets        = var.sink_service_subnets
  sink_security_group_default = var.sink_security_group_default

  ############## definicoes basicas do container
  sink_task_profile_compute_config = {
    profile = var.profile
  }

  ############## configuracoes de propriedades do connector
  sink_comunidade                              = local.sink_comunidade
  sink_sigla                                   = local.sink_sigla
  sink_kafka_renew_certificate_client_user     = local.secret_string["kcert.user"]
  sink_kafka_renew_certificate_client_password = local.secret_string["kcert.password"]
  sink_kafka_client_id                         = var.sink_kafka_client_id
  sink_kafka_group_id                          = var.sink_kafka_group_id
  sink_kafka_topic_filter                      = local.sink_kafka_topic_filter
  sink_schema_topics_properties                = var.sink_schema_topics
  sink_schema_less_topics_properties           = var.sink_schema_less_topics
  sink_messaging_service                       = local.sink_messaging_service
  sink_messaging_arn                           = var.sink_messaging_arn
  sink_messaging_fifo                          = local.sink_messaging_fifo
  sink_observability_backend                   = local.sink_observability_backend
  sink_observability_trace_enabled             = local.sink_observability_trace_enabled
  sink_datadog_custom_config                   = var.sink_datadog_custom_config
  sink_rate_limit_enabled                      = var.sink_rate_limit_enabled
  sink_rate_limit_standard_message_quotas      = var.sink_rate_limit_standard_message_quotas
  sink_rate_limit_wait_timeout                 = var.sink_rate_limit_wait_timeout

  ############## tags obrigatorias
  sink_context               = local.sink_context
  sink_owner_contact_email   = local.sink_owner_contact_email
  sink_tech_team_email       = local.sink_tech_team_email
  sink_finalidade            = local.sink_finalidade
  sink_squad                 = local.sink_squad
  sink_additional_tags       = var.sink_additional_tags
  github_repo_id             = var.github_repo_id
  github_repo_name           = var.github_repo_name
  sink_output                = var.sink_output
  sink_transformation_filter = local.sink_transformation_filter_data
  sink_logging               = var.sink_logging

  ############## Graviton
  sink_task_runtime_platform = {
    operatingSystemFamily = "LINUX"
    cpuArchitecture       = "ARM64"
  }
}
