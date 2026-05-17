"""Multi-tenant configuration helpers."""
from __future__ import annotations

import os
from typing import Any, Dict, List

DEFAULT_TENANTS = [
    {"tenant_key": "national-demo", "name": "전국형 데모", "region_scope": "전국", "theme": "green"},
    {"tenant_key": "seoul-demo", "name": "서울 청년지원 데모", "region_scope": "서울", "theme": "mint"},
    {"tenant_key": "university-demo", "name": "대학 학생지원 데모", "region_scope": "campus", "theme": "lime"},
]


def current_tenant() -> Dict[str, Any]:
    key = os.getenv("LIFEPASS_TENANT_KEY", "national-demo")
    for tenant in DEFAULT_TENANTS:
        if tenant["tenant_key"] == key:
            return tenant
    return {"tenant_key": key, "name": key, "region_scope": "custom", "theme": "green"}


def tenant_rows() -> List[Dict[str, Any]]:
    rows = list(DEFAULT_TENANTS)
    current = current_tenant()
    for row in rows:
        row["active"] = row["tenant_key"] == current["tenant_key"]
    if not any(r["active"] for r in rows):
        rows.append({**current, "active": True})
    return rows
