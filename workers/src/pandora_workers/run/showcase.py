"""ShowcaseAgent entry point — Phase 7.2."""

from pandora_workers.agents.showcase import ShowcaseAgent
from pandora_workers.run._bootstrap import run_or_exit

if __name__ == "__main__":
    run_or_exit(ShowcaseAgent, phase="Phase 7", step="7.2")
