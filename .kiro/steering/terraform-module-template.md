# Terraform Module Standards

## Module Structure

Every Terraform module follows this layout:

```
infrastructure/terraform/
├── environments/
│   ├── dev/
│   │   └── terraform.tfvars
│   ├── stage/
│   │   └── terraform.tfvars
│   └── prod/
│       └── terraform.tfvars
├── modules/
│   ├── networking/
│   ├── compute/
│   ├── data-stores/
│   ├── secrets/
│   ├── observability/
│   └── security/
├── main.tf
├── variables.tf
├── outputs.tf
├── providers.tf
├── backend.tf
└── versions.tf
```

## Module Template

```hcl
# modules/<name>/main.tf
resource "aws_<resource>" "this" {
  # Use "this" for single-instance resources
  name = "${var.project}-${var.environment}-<resource>"
  tags = local.common_tags
}

locals {
  common_tags = {
    Project     = var.project
    Environment = var.environment
    ManagedBy   = "terraform"
    Module      = "<module-name>"
  }
}
```

## Naming Conventions

- Resources: `${project}-${environment}-${purpose}`
- Variables: snake_case, prefixed by category (`vpc_cidr`, `ecs_cpu`, `db_instance_class`)
- Outputs: `<resource>_<attribute>` (e.g., `vpc_id`, `alb_dns_name`)
- Modules: singular noun (`networking`, `compute`, `security`)

## Backend Configuration

```hcl
terraform {
  backend "s3" {
    bucket         = "rag-pipeline-terraform-state"
    key            = "environments/${var.environment}/terraform.tfstate"
    region         = "ap-southeast-2"
    dynamodb_table = "terraform-locks"
    encrypt        = true
  }
}
```

## Required Variables (every module)

```hcl
variable "project" {
  type    = string
  default = "rag-pipeline"
}

variable "environment" {
  type = string
  validation {
    condition     = contains(["dev", "stage", "prod"], var.environment)
    error_message = "Environment must be dev, stage, or prod."
  }
}

variable "region" {
  type    = string
  default = "ap-southeast-2"
}
```

## Security Defaults

- All S3 buckets: `server_side_encryption_configuration` with AES-256
- All RDS/Neptune: `storage_encrypted = true`
- All security groups: deny all inbound by default, allow only required ports
- All IAM policies: least-privilege, no wildcards in production
- TLS 1.2+ minimum for all listeners
