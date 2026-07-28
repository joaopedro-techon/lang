locals {

  sigla = "XXX"

  sigla_app = "XXX-XXXXX"

  produto = "Nome do produto"

  context = "context"

  owner_contact_email = "owner-contact-email@itau-unibanco.com.br"

  tech_team_email = "tech-team-email@itau-unibanco.com.br"

  finalidade = "modernizacao"

  squad = "squad"

  feature_name = "feature"

  microservice_name = "microservice"

  additional_tags = {
    "sigla-app" = local.sigla_app
  }

  default_container_port = (
    var.task_container_port[0].hostPort == null
    ? var.task_container_port[0].containerPort
    : var.task_container_port[0].hostPort
  )

  task_health_check = {
    command = ["CMD-SHELL", "curl -f http://localhost:${local.default_container_port}/actuator/health || exit 1"]
  }

  task_environment_vars = [

  ]

  tg_groups_config = [
    {
      protocol = "TCP"
      port     = local.default_container_port
      health_check = {
        protocol            = "HTTP"
        port                = local.default_container_port
        path                = "/actuator/health"
        interval            = 30
        healthy_threshold   = 5
        unhealthy_threshold = 2
        matcher             = "200-299"
        timeout             = 5
      }
    }
  ]

  lb_listeners_config = [
    {
      load_balancer_arn = data.aws_lb.nlb.arn
      protocol          = "TCP"
    }
  ]
}
