module "iamsr_module" {
  source = "git::https://github.com/itau-corp/itau-ey4-modulo-iamsr.git?ref=v3.0.0"
  policies = [
    {
      name     = "${local.feature_name}-${local.microservice_name}-execution-autoscale-policy"
      document = "iamsr/policy/policy-execution-autoscale.json"
      path     = "/"
    },
    {
      name     = "${local.feature_name}-${local.microservice_name}-execution-ecs-policy"
      document = "iamsr/policy/policy-execution-ecs.json"
      path     = "/"
    }
  ]
  roles = [
    {
      name                  = "${local.feature_name}-${local.microservice_name}-execution-autoscale-role"
      trust_policy_document = "iamsr/trust/trust-execution-autoscale.json"
      path                  = "/"
      attached_policies = [
        "arn:aws:iam::${data.aws_caller_identity.current.account_id}:policy/iamsr/${local.feature_name}-${local.microservice_name}-execution-autoscale-policy"
      ]
    },
    {
      name                  = "${local.feature_name}-${local.microservice_name}-execution-ecs-role"
      trust_policy_document = "iamsr/trust/trust-execution-ecs.json"
      path                  = "/"
      attached_policies = [
        "arn:aws:iam::${data.aws_caller_identity.current.account_id}:policy/iamsr/${local.feature_name}-${local.microservice_name}-execution-ecs-policy"
      ]
    }
  ]
}
