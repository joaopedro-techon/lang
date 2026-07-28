############## definições basicas do service
environment = "hom"

ecs_cluster_name = "ecs-cluster"

service_desired_count = 1

service_launch_config = {
  launch_type = "FARGATE"
  capacity_providers = [
    {
      capacity_provider = "FARGATE_SPOT"
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

security_group_default = "sg-00000000000000000"

task_container_port = [
  {
    containerPort = 2000
  }
]

############## definições basicas do container
task_cpu = 512

task_memory = 1024

task_ulimits_vars = [
  {
    name      = "nofile"
    softLimit = 2048
    hardLimit = 8192
  }
]

task_log_driver = {
  log-driver = "splunk"
  options = {
    splunk-index = "raw_xxx"
    tag          = " "
  }
  secret-options = {
    splunk-token = "arn:aws:secretsmanager:sa-east-1:000000000000:secret:splunk-log-token"
  }
}
