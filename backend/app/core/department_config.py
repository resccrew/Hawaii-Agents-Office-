"""Loads studio.toml — department/repo mapping, ported from claude-office's
floor_config.py (backend/floors.toml -> [[floors]]) renamed to departments."""

from __future__ import annotations

import tomllib
from pathlib import Path

from pydantic import BaseModel


class DepartmentConfig(BaseModel):
    name: str
    floor_number: int
    accent: str
    icon: str
    repos: list[str] = []


class StudioConfig(BaseModel):
    studio_name: str
    departments: list[DepartmentConfig] = []

    def department_for_repo(self, repo_name: str) -> DepartmentConfig | None:
        for dept in self.departments:
            if repo_name in dept.repos:
                return dept
        return None


def load_studio_config(path: str | Path) -> StudioConfig:
    path = Path(path)
    with path.open("rb") as f:
        raw = tomllib.load(f)
    departments = [DepartmentConfig(**d) for d in raw.get("departments", raw.get("floors", []))]
    return StudioConfig(studio_name=raw.get("studio_name", raw.get("building_name", "Studio")), departments=departments)
