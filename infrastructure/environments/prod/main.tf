terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = { source = "hashicorp/aws"; version = "~> 5.0" }
  }
  backend "s3" {
    bucket         = "rag-pipeline-terraform-state"
    key            = "prod/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "rag-pipeline-terraform-locks"
    encrypt        = true
  }
}

provider "aws" { region = "us-east-1" }

module "networking" {
  source      = "../../modules/networking"
  environment = "prod"
}

module "compute" {
  source            = "../../modules/compute"
  environment       = "prod"
  vpc_id            = module.networking.vpc_id
  subnet_ids        = module.networking.private_subnet_ids
  security_group_id = module.networking.api_security_group_id
  container_image   = "rag-pipeline-api:latest"
  desired_count     = 3
  cpu               = 2048
  memory            = 4096
}

output "api_url" { value = "http://${module.compute.alb_dns_name}" }
