# v5 Upgrade Notes

v5는 v4의 PostgreSQL/pgvector-ready 구조, Agent workflow, 스마트 매퍼, 문서 파서, Guardrails 위에 다음 운영형 고급 기술을 추가했다.

## Added

- Event Mesh / Transactional Outbox demo
- Policy Digital Twin for pre-enactment impact simulation
- Zero-Trust RBAC/ABAC access-control pack
- Differential Privacy aggregate release demo
- Synthetic profile generation for privacy-safe testing
- Causal intervention ranking for next-best counseling actions
- Data Contract, Model Card, SLA/Incident Playbook
- New FastAPI endpoints for v5 modules
- PostgreSQL initialization schema under `infra/postgres/init.sql`
- Redis service in `docker-compose.yml`
- README rewritten for judge-facing competition submission

## Recommended run command

```bash
docker compose up -d --build
```

## Verification

```bash
python -m py_compile app.py api.py core/*.py cli_demo.py tests/verify_mvp.py
python tests/verify_mvp.py
```
