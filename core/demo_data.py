"""Sample-profile loader."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

from .models import UserProfile

DEFAULT_SAMPLE_PATH = Path(__file__).resolve().parents[1] / "data" / "sample_profiles.json"


def load_sample_profiles(path: str | Path = DEFAULT_SAMPLE_PATH) -> List[Dict]:
    with Path(path).open("r", encoding="utf-8") as f:
        return json.load(f)


def sample_profiles_as_models(path: str | Path = DEFAULT_SAMPLE_PATH) -> List[UserProfile]:
    return [UserProfile.from_dict(item["profile"]) for item in load_sample_profiles(path)]
