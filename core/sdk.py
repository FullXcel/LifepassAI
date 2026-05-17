"""Tiny Python SDK example for API-first integration."""
from __future__ import annotations

import json
import urllib.request
from typing import Any, Dict


class LifePassClient:
    def __init__(self, base_url: str = "http://localhost:8000") -> None:
        self.base_url = base_url.rstrip("/")

    def analyze(self, profile: Dict[str, Any], question: str = "") -> Dict[str, Any]:
        data = json.dumps({"profile": profile, "question": question}).encode("utf-8")
        req = urllib.request.Request(f"{self.base_url}/api/v1/analyze", data=data, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 - local SDK demo
            return json.loads(resp.read().decode("utf-8"))


def curl_examples() -> str:
    return """curl -X POST http://localhost:8000/api/v1/analyze \\
  -H 'Content-Type: application/json' \\
  -d '{"profile":{"age":27,"region":"서울","monthly_income":0,"rent":550000},"question":"먼저 신청할 혜택은?"}'

curl 'http://localhost:8000/api/v1/policies/search?q=청년%20월세&top_k=5'
""".strip()
