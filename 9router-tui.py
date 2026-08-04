#!/usr/bin/env python3
"""
9router-tui.py — interactive terminal menu for the 9router CLI.

Runs a numbered menu that calls into 9router.py (the same modular core),
so every command behaves exactly like the CLI version.

Usage:
  python 9router-tui.py

Menu:
  1. up        Deploy N services
  2. sync      Re-configure existing services
  3. list      Show saved services (URL + keys)
  4. keys      Show only API keys
  5. status    Live Railway status
  6. test      Send a real request to a service
  7. down      Delete service(s)
  8. nuke      Delete the entire project (fix stuck volumes)
  9. clean     Delete detached volumes
  10. setpass  Change default password
  11. config   Show settings
  12. token    Show token status
  13. reset    Clear state.json
  0. exit
"""

import os
import subprocess
import sys
from pathlib import Path

DIR = Path(__file__).resolve().parent
CORE = DIR / "9router.py"

MENU = [
    ("up",      "Deploy N services"),
    ("sync",    "Re-configure existing services"),
    ("list",    "Show saved services (URL + API keys)"),
    ("keys",    "Show only API keys"),
    ("status",  "Live Railway status"),
    ("test",    "Send a real request to a service"),
    ("down",    "Delete service(s)"),
    ("nuke",    "Delete the ENTIRE project (fixes stuck volumes)"),
    ("clean",   "Delete detached volumes"),
    ("setpass", "Change default dashboard password"),
    ("config",  "Show current settings"),
    ("token",   "Show token status"),
    ("reset",   "Clear state.json"),
]


def clear():
    os.system("cls" if os.name == "nt" else "clear")


def run_core(args):
    """Run the core CLI in this same process (import) so state/settings stay
    consistent and output streams directly."""
    sys.argv = ["9router.py", *args]
    os.environ.setdefault("RAILWAY_API_TOKEN", "")
    # simplest & most faithful: exec the core module
    code = compile(CORE.read_text(encoding="utf-8"), str(CORE), "exec")
    exec(code, {"__name__": "__main__", "__file__": str(CORE)})


def ask(question: str, default: str = "") -> str:
    """Prompt the user, returning input (or default on empty)."""
    suffix = f" [{default}]" if default else ""
    try:
        return input(f"  {question}{suffix}: ").strip() or default
    except (KeyboardInterrupt, EOFError):
        return ""


def confirm(question: str) -> bool:
    ans = input(f"  {question} [y/N]: ").strip().lower()
    return ans in ("y", "yes")


def interactive_action(cmd: str):
    """Get extra args for commands that need them, then run."""
    if cmd == "up":
        n = ask("How many services?", "1")
        if n.isdigit() and int(n) > 0:
            run_core(["up", n])
        else:
            print("  ❌ invalid count")
    elif cmd == "down":
        target = ask("Which service? (name | 'all')")
        if target:
            if target != "all" and not confirm(f"Delete service '{target}'?"):
                print("  skipped")
                return
            run_core(["down", target])
        else:
            print("  ❌ no name given")
    elif cmd == "nuke":
        if confirm("NUKE deletes the ENTIRE project. Are you sure?"):
            run_core(["nuke"])
        else:
            print("  skipped")
    elif cmd == "setpass":
        new = ask("New default password?")
        if new:
            run_core(["setpass", new])
        else:
            print("  ❌ empty password")
    elif cmd == "test":
        target = ask("Service name (empty = first):")
        run_core(["test", target])
    elif cmd == "clean":
        run_core(["clean"])
    elif cmd == "reset":
        if confirm("Clear state.json? (services are NOT touched)"):
            run_core(["reset"])
        else:
            print("  skipped")
    else:
        run_core([cmd])


def main():
    while True:
        clear()
        print("╔" + "═" * 50 + "╗")
        print("║        9ROUTER MANAGER — Terminal Menu         ║")
        print("╚" + "═" * 50 + "╝")
        print()
        for i, (cmd, desc) in enumerate(MENU, 1):
            print(f"  {i:>2}. {cmd:<8} — {desc}")
        print(f"  {0:>2}. exit")
        print()
        choice = input("  Choice [0-13]: ").strip()

        if choice == "0" or choice.lower() == "exit" or choice == "":
            print("\n  bye 👋")
            break

        if not choice.isdigit() or not (1 <= int(choice) <= len(MENU)):
            print("  ❌ invalid choice")
            input("  [press Enter]")
            continue

        cmd = MENU[int(choice) - 1][0]
        print()
        interactive_action(cmd)
        print()
        input("  [press Enter to continue]")


if __name__ == "__main__":
    main()
