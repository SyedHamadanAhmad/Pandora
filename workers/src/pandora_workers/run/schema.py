"""SchemaAgent entry point — Phase 5.2."""

from pandora_workers.agents.schema import SchemaAgent
from pandora_workers.run._bootstrap import run_or_exit

if __name__ == "__main__":
    run_or_exit(SchemaAgent, phase="Phase 5", step="5.2")
