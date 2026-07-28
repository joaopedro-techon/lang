output "service_default" {
  value     = module.ecs-worker-task.service_default
  sensitive = true
}

output "task_definition" {
  value     = module.ecs-worker-task.task_definition
  sensitive = true
}

output "appspec" {
  value     = module.ecs-worker-task.appspec
  sensitive = true
}

output "service_name" {
  value = module.ecs-worker-task.service_name
}

output "cluster_name" {
  value = module.ecs-worker-task.cluster_name
}

output "codedeploy_application" {
  value = module.ecs-worker-task.codedeploy_application
}

output "codedeploy_group" {
  value = module.ecs-worker-task.codedeploy_group
}

output "codedeploy_strategy" {
  value = module.ecs-worker-task.codedeploy_strategy
}
