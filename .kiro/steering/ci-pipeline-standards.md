# CI/CD Pipeline Standards (GitLab CI)

## Stage Naming

Stages follow verb-noun pattern in execution order:

```yaml
stages:
  - build
  - test-unit
  - scan-security
  - test-contract
  - test-integration
  - scan-dast
  - test-e2e
  - evaluate
  - test-performance
  - test-accessibility
  - package
  - deploy-dev
  - deploy-stage
  - deploy-prod
```

## Job Template

```yaml
.job-template:
  image: python:3.11-slim
  tags: [docker]
  variables:
    PIP_CACHE_DIR: "$CI_PROJECT_DIR/.pip-cache"
  cache:
    key: ${CI_COMMIT_REF_SLUG}
    paths:
      - .pip-cache/
      - .venv/
  before_script:
    - pip install --upgrade pip
    - pip install -e ".[dev,test]"
```

## Artifact Passing

- Unit test reports: `reports/junit-unit.xml`
- Coverage: `reports/coverage.xml` + `htmlcov/`
- SAST findings: `reports/sast.json`
- SCA/SBOM: `reports/sbom.json`
- Container scan: `reports/container-scan.json`
- Evaluation metrics: `reports/eval-metrics.json`
- Performance results: `reports/k6-results.json`

## Gate Conditions

| Gate | Condition | Blocks |
|------|-----------|--------|
| Unit tests | 100% pass | All downstream |
| Coverage | >= 80% lines | merge to main |
| SAST | 0 critical/high | merge to main |
| SCA | 0 critical CVEs | merge to main |
| Secrets | 0 findings | merge to main |
| Contract | 0 divergence | deploy |
| Eval regression | < 5% drop on any metric | deploy to prod |
| Performance | p95 < 2s for /ask | deploy to prod |

## Environment Promotion

```
dev (auto) → stage (auto on main) → prod (manual gate + approval)
```

- Dev: deploy on every push to feature branches
- Stage: deploy on merge to main (auto)
- Prod: manual trigger with required approval from 1+ reviewer

## Rollback Strategy

```yaml
deploy-prod:
  script:
    - terraform apply -auto-approve
    - ./scripts/post-deploy-verify.sh
  after_script:
    - if [ $CI_JOB_STATUS == "failed" ]; then terraform apply -auto-approve -var="image_tag=$PREVIOUS_TAG"; fi
```

## Security Scanning Tools

| Tool | Purpose | Stage |
|------|---------|-------|
| Semgrep | SAST (Python patterns) | scan-security |
| Bandit | Python security linting | scan-security |
| Trivy | Container image scanning | scan-security |
| Checkov | IaC scanning (Terraform) | scan-security |
| Gitleaks | Secret detection | scan-security |
| OWASP ZAP | DAST | scan-dast |
| Schemathesis | API contract fuzzing | test-contract |
