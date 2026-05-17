"""Postgres-aligned enums (Tech Spec v1.7 §4.1)."""

from enum import Enum


class ProjectStatus(str, Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"


class ComponentStatus(str, Enum):
    generating = "generating"
    validating = "validating"
    validated = "validated"
    failed = "failed"
    revised = "revised"


class MessageRole(str, Enum):
    user = "user"
    system = "system"
