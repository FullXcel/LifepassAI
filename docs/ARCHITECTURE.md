# LifePass v5 Architecture

LifePass v5 is organized as a competition-grade welfare operations platform.

```text
Streamlit UI
  -> FastAPI backend
  -> Core rule/agent/optimization modules
  -> PostgreSQL + pgvector + Redis-ready infrastructure
```

## v5 additions

1. **Event Mesh**: every profile or policy signal is converted into an event envelope with routing key, idempotency key, trace id and schema version.
2. **Transactional Outbox**: delivery rows are separated from business decisions so event publishing can be retried safely.
3. **Policy Digital Twin**: proposed policy changes are simulated against sample profiles before release.
4. **Zero-Trust Controls**: role, purpose and field-level access checks govern sensitive profile access.
5. **Privacy Layer**: aggregate releases can use privacy-budget style controls and synthetic profiles are generated for demos.
6. **Causal Ops**: counseling interventions are ranked with a transparent uplift/ROI proxy.
7. **Quality Ops**: data contract, model card and incident playbook make the project reviewable as an operational system.
```
