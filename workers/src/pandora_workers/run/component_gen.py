"""ComponentGenAgent entry point — Phase 6.1."""

from pandora_workers.agents.component_gen import ComponentGenAgent
from pandora_workers.run._bootstrap import run_or_exit

if __name__ == "__main__":
    run_or_exit(ComponentGenAgent, phase="Phase 6", step="6.1")
