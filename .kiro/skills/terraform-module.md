---
inclusion: manual
---

# Skill: Terraform Module Implementation

## Purpose
Create or update a Terraform module following the project's IaC conventions with proper naming, tagging, encryption, and variable validation.

## Process

1. **Create module directory** — `infrastructure/modules/<module-name>/`
2. **Define variables** — `variables.tf` with validation blocks
3. **Define resources** — `main.tf` with common tags
4. **Define outputs** — `outputs.tf` with descriptions
5. **Add provider constraints** — `versions.tf`
6. **Add environment tfvars** — `infrastructure/environments/<env>/terraform.tfvars`
7. **Validate** — `terraform fmt -check && terraform validate`

## Module Template

### variables.tf

```hcl
variable "project" {
  type        = string
  default     = "rag-pipeline"
  description = "Project name used in resource naming"
}

variable "environment" {
  type        = string
  description = "Deployment environment"
  validation {
    condition     = contains(["dev", "stage", "prod"], var.environment)
    error_message = "Environment must be dev, stage, or prod."
  }
}

variable "region" {
  type        = string
  default     = "ap-southeast-2"
  description = "AWS region for resources"
}
```

### main.tf

```hcl
locals {
  name_prefix = "${var.project}-${var.environment}"
  common_tags = {
    Project     = var.project
    Environment = var.environment
    ManagedBy   = "terraform"
    Module      = "<module-name>"
  }
}

resource "aws_<resource>" "this" {
  name = "${local.name_prefix}-<purpose>"
  tags = local.common_tags
}
```

### outputs.tf

```hcl
output "<resource>_id" {
  description = "ID of the <resource>"
  value       = aws_<resource>.this.id
}

output "<resource>_arn" {
  description = "ARN of the <resource>"
  value       = aws_<resource>.this.arn
}
```

## Security Checklist

- [ ] Encryption at rest enabled (AES-256 or KMS)
- [ ] TLS 1.2+ for all in-transit communication
- [ ] Security groups deny all by default
- [ ] IAM policies follow least-privilege
- [ ] Sensitive outputs marked `sensitive = true`
- [ ] No hardcoded secrets in .tf files
