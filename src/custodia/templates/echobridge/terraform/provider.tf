terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 4.40.0, != 5.59.0, != 5.60.0, <= 5.64.0"
    }
  }

  required_version = ">= 1.5.7"
}
