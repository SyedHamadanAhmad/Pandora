"""VerificationAgent entry point — Phase 7.1."""

from pandora_workers.agents.verification import VerificationAgent
from pandora_workers.run._bootstrap import run_or_exit

if __name__ == "__main__":
    run_or_exit(VerificationAgent, phase="Phase 7", step="7.1")
