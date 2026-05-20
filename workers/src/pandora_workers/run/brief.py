"""DesignBriefAgent entry point — Phase 5.1."""

from pandora_workers.agents.brief import BriefAgent
from pandora_workers.run._bootstrap import run_or_exit

if __name__ == "__main__":
    run_or_exit(BriefAgent, phase="Phase 5", step="5.1")
