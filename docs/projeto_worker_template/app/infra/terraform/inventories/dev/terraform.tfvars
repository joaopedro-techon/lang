############## definições basicas do service
environment = "dev"

ecs_cluster_name = "ecs-cluster"

service_desired_count = 1

autoscaling = {
  min_capacity = 1
  max_capacity = 3
  scale_up = {
    threshold          = 4000 # threshold = concorrencia por task / tempo
    cooldown           = 60
    evaluation_periods = 1
    steps = [
      { lower_bound = 0, upper_bound = null, scaling_adjustment = 1 }
    ]
  }
  scale_down = {
    threshold          = 500
    cooldown           = 1200
    evaluation_periods = 5
    steps = [
      { lower_bound = null, upper_bound = 0, scaling_adjustment = -1 }
    ]
  }
  queue_names = ["queue_name"]
}

service_launch_config = {
  launch_type = "FARGATE"
  capacity_providers = [
    {
      capacity_provider = "FARGATE"
      base              = 1
      weight            = 1
    }
  ]
}

############## configurações minimas de rede
service_vpc_id = "vpc-00000000000000000"

service_cidr_blocks = [
  "xxx.xxx.xxx.xxx/xx",
  "yyy.yyy.yyy.yyy/yy",
  "zzz.zzz.zzz.zzz/zz"
]

service_subnets = [
  "subnet-0000000000000000a",
  "subnet-0000000000000000b",
  "subnet-0000000000000000c"
]

task_container_port = [
  {
    containerPort = 8006
  }
]

############## definições basicas do container
task_cpu = 1024

task_memory = 2048

task_ulimits_vars = [
  {
    name      = "nofile"
    softLimit = 2048
    hardLimit = 8192
  }
]

task_ephemeral_storage_size_in_gib = 50
