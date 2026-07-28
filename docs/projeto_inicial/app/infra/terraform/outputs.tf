#### É extremamente necessário utilizar os outputs abaixo conforme a estratégia de deploy escolhida.
#### A remoção ou configuração incorreta causará falha na etapa de deployment do ecs
#### Escolha qual o tipo de estratégia será utilizada (codedeploy/worker ou worker gradual), e comente os demais.

########################################
#### Para módulos codedeploy/worker ####
########################################
output "task_definition" {
  value     = module.ecs-app-task.task_definition
  sensitive = true
}

output "appspec" {
  value     = module.ecs-app-task.appspec
  sensitive = true
}

output "service_name" {
  value = module.ecs-app-task.service_name
}

output "cluster_name" {
  value = module.ecs-app-task.cluster_name
}

output "codedeploy_application" {
  value = module.ecs-app-task.codedeploy_application
}

output "codedeploy_group" {
  value = module.ecs-app-task.codedeploy_group
}

output "codedeploy_strategy" {
  value = module.ecs-app-task.codedeploy_strategy
}

####################################
#### Para módulo worker-gradual ####
####################################
# output "service_names" {
#   value       = module.ecs-worker-gradual-task.service_names
#   description = "Name of the services created for the workload"
# }

# output "taskset_subnets" {
#   value       = module.ecs-worker-gradual-task.taskset_subnets
#   description = "Task Subnets"
# }

# output "taskset_security_groups" {
#   value       = module.ecs-worker-gradual-task.taskset_security_groups
#   description = "Task Security Groups"
# }

# output "bake_alarm" {
#   value = module.ecs-worker-gradual-task.bake_alarm
# }

# output "check_health_alarm" {
#   value = module.ecs-worker-gradual-task.check_health_alarm
# }

# output "taskset_capacity_provider" {
#   value     = module.ecs-worker-gradual-task.taskset_capacity_provider
#   sensitive = true
# }
