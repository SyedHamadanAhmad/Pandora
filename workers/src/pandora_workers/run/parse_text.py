"""TextParserAgent entry point."""

from pandora_workers.agents.parse_text import ParseTextAgent
from pandora_workers.run._bootstrap import run_or_exit

if __name__ == "__main__":
    run_or_exit(ParseTextAgent, phase="Phase 4", step="4.1")
