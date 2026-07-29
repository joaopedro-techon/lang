############## definições basicas do service
environment = "dev"

ecs_cluster_name = "ecs-cluster" // [PARAMETRO_IA - Deve listar opções da AWS]

service_desired_count = 1

autoscaling = { // [PARAMETRO_IA - Deve perguntar para o usuário a quantidade de chamadas por segunda que o worker irá processar. O calculo deve ser feito pel proprio agente de acordo com o backlog da fila SQS]
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
  queue_names = ["queue_name"]  // [PARAMETRO_IA - Deve perguntar ao usuário as filas SQS que serão verificadas no auto scaling]
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
service_vpc_id = "vpc-00000000000000000" //[PARAMETRO_IA - Deve listar opções da AWS]

service_cidr_blocks = [ // [PARAMETRO_IA - Deve listar opções da AWS]
  "xxx.xxx.xxx.xxx/xx",
  "yyy.yyy.yyy.yyy/yy",
  "zzz.zzz.zzz.zzz/zz"
]

service_subnets = [ // [PARAMETRO_IA - Deve listar opções da AWS]
  "subnet-0000000000000000a",
  "subnet-0000000000000000b",
  "subnet-0000000000000000c"
]

task_container_port = [ // [PARAMETRO_IA - Deve perguntar a porta do container para o usuario]
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
