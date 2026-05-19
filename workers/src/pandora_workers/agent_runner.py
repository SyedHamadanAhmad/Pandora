"""Bootstrap and run one or more ``BaseAgent`` consumers."""

from __future__ import annotations

import asyncio
import logging

from pandora_workers.base_agent import BaseAgent
from pandora_workers.runtime import configure_logging, connect, declare_topology, run_consumers

logger = logging.getLogger(__name__)


async def run_agents(agents: list[BaseAgent]) -> None:
    connection = await connect()
    async with connection:
        channel = await connection.channel()
        await declare_topology(channel)
        bindings = [agent.binding() for agent in agents]
        logger.info(
            "starting agents: %s",
            ", ".join(f"{q}→{agent.result_queue}" for q, agent in zip(
                (b[0] for b in bindings), agents, strict=True
            )),
        )
        await run_consumers(connection, bindings)


def main(*agents: BaseAgent, log_name: str = "pandora_workers") -> None:
    configure_logging(log_name)
    if not agents:
        raise SystemExit("No agents configured")
    try:
        asyncio.run(run_agents(list(agents)))
    except KeyboardInterrupt:
        logger.info("shutting down agents")
