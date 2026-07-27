---
inclusion: manual
---

# Skill: GitLab CI Stage Implementation

## Purpose
Create or update a GitLab CI pipeline stage following the project's CI/CD standards with proper artifact passing, gate conditions, and caching.

## Process

1. **Identify stage** — Which pipeline stage from `.gitlab-ci.yml`?
2. **Choose base image** — Python, Node, Docker, or custom
3. **Define job script** — Commands to execute
4. **Configure artifacts** — Reports, coverage, binaries
5. **Set rules** — Branch conditions, manual gates
6. **Add caching** — pip/npm/node_modules cache
7. **Define dependencies** — Which prior stages this job needs

## Job Template

```yaml
<stage-name>:
  stage: <stage>
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
  script:
    - <commands>
  artifacts:
    when: always
    reports:
      junit: reports/<report-name>.xml
    paths:
      - reports/
    expire_in: 7 days
  rules:
    - if: $CI_PIPELINE_SOURCE == "merge_request_event"
    - if: $CI_COMMIT_BRANCH == "main"
```

## Gate Conditions

| Stage | Failure Behavior |
|-------|-----------------|
| test-unit | Block all downstream |
| scan-security | Block merge (critical/high) |
| test-contract | Block deploy |
| evaluate | Block prod deploy (>5% regression) |
| test-performance | Block prod deploy (p95 > 2s) |
| deploy-prod | Manual gate + approval required |

## Checklist

- [ ] Job has explicit `stage:` field
- [ ] Artifacts configured with `expire_in`
- [ ] JUnit reports for test stages
- [ ] Cache configured for package manager
- [ ] Rules restrict when job runs
- [ ] `allow_failure: false` for security gates
- [ ] Deploy jobs have rollback in `after_script`
- [ ] Environment name set for deploy jobs
