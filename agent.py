"""Thin CLI entry: interactive Tier-2 task agent against a single part studio.

Usage:
    python agent.py <did> <wid> <eid>                # interactive
    python agent.py <did> <wid> <eid> "<prompt>"     # one-shot
"""
import sys
from onshape_agent import OnshapeClient
from onshape_agent.llm import AnthropicChat
from onshape_agent.agents import TaskAgent


def main():
    if len(sys.argv) < 4:
        print(__doc__)
        sys.exit(1)
    did, wid, eid = sys.argv[1:4]
    prompt_arg = " ".join(sys.argv[4:]) if len(sys.argv) > 4 else None

    client = OnshapeClient()
    chat = AnthropicChat()
    agent = TaskAgent(chat, client)

    def wrap(p):
        return (f"Document IDs: document_id={did}, workspace_id={wid}, "
                f"element_id={eid}\n\nUser request: {p}")

    if prompt_arg:
        print(agent.run(wrap(prompt_arg)))
        return

    print(f"Onshape task agent ({did[:8]}/{wid[:8]}/{eid[:8]}) — 'exit' to quit")
    while True:
        try:
            p = input("> ").strip()
        except EOFError:
            break
        if not p or p in ("exit", "quit"):
            break
        try:
            print(f"\n{agent.run(wrap(p))}\n")
        except Exception as e:
            print(f"[error] {type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
