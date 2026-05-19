"""Shared bootstrap for worker entry modules."""

from __future__ import annotations

import sys

from pandora_workers.agent_runner import main as run_main
from pandora_workers.base_agent import BaseAgent


def run_or_exit(agent_cls: type[BaseAgent], *, phase: str, step: str) -> None:
    try:
        agent = agent_cls()
    except NotImplementedError as exc:
        print(f"{agent_cls.__name__}: {exc} ({phase} {step})", file=sys.stderr)
        sys.exit(1)
    run_main(agent, log_name=agent_cls.__module__)
