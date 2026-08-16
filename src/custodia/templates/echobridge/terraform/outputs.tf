output "task_definition" {
  value     = module.ecs-sink-connector.task_definition
  sensitive = true
}

output "appspec" {
  value     = module.ecs-sink-connector.appspec
  sensitive = true
}

output "service_name" {
  value = module.ecs-sink-connector.service_name
}

output "cluster_name" {
  value = module.ecs-sink-connector.cluster_name
}

output "codedeploy_application" {
  value = module.ecs-sink-connector.codedeploy_application
}

output "codedeploy_group" {
  value = module.ecs-sink-connector.codedeploy_group
}

output "codedeploy_strategy" {
  value = module.ecs-sink-connector.codedeploy_strategy
}

output "kcert_user" {
  value     = local.secret_string["kcert.user"]
  sensitive = true
}

output "kcert_password" {
  value     = local.secret_string["kcert.password"]
  sensitive = true
}
