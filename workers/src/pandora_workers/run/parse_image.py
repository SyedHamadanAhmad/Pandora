"""ImageParserAgent entry point."""

from pandora_workers.agents.parse_image import ParseImageAgent
from pandora_workers.run._bootstrap import run_or_exit

if __name__ == "__main__":
    run_or_exit(ParseImageAgent, phase="Phase 4", step="4.2")
