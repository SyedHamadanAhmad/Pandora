"""FeedbackAgent entry point — Phase 6.2."""

from pandora_workers.agents.feedback import FeedbackAgent
from pandora_workers.run._bootstrap import run_or_exit

if __name__ == "__main__":
    run_or_exit(FeedbackAgent, phase="Phase 6", step="6.2")
