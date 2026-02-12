import getpass
import shlex
from typing import Any, Dict, List

from crypto_store import load_db_file, save_db_file, CryptoStoreError
from db import (
    new_db,
    add_entry_one_per_day,
    delete_entry,
    entry_day,
    entries_for_metric,
    normalize_type,
    parse_day,
    recent_entries,
)
from graph import render_value_wick_graph_10


import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "storage.enc")


HELP_TEXT = """Commands:
  addweight <kg> [YYYY-MM-DD] [silent]      Add weight (one entry per day)
  addpulls <reps> [YYYY-MM-DD] [silent]     Add pull-ups (one entry per day)
  addpushes <reps> [YYYY-MM-DD] [silent]    Add push-ups (one entry per day)

  overview                                  Show overview (includes graphs)
  weight                                    Show weight (summary + graph)
  pulls                                     Show pulls (summary + graph)
  pushes                                    Show pushes (summary + graph)

  recent [N]                                Show last N entries (default 5)
  delete <id>                               Delete an entry by id (use 'recent' to find ids)

  help                                      Show this help
  quit                                      Exit

Notes:
  - Date must be YYYY-MM-DD (no brackets).
  - One entry per metric per day is enforced.
"""


def require_password() -> str:
    pw = getpass.getpass("Password: ")
    if not pw:
        raise SystemExit("Empty password not allowed.")
    return pw


def parse_command(line: str) -> List[str]:
    return shlex.split(line.strip())


def metric_summary(db: Dict[str, Any], metric_type: str) -> List[str]:
    t = normalize_type(metric_type)
    unit = "kg" if t == "weight" else "reps"
    es = entries_for_metric(db, t)
    if not es:
        return [f"{t}: (no data)"]
    latest = es[-1]
    latest_val = float(latest["value"])
    latest_str = f"{latest_val:.2f}" if t == "weight" else f"{latest_val:g}"
    return [
        f"{t}: latest {latest_str} {unit} ({latest['ts']})",
        f"{t}: total entries {len(es)}",
    ]


def print_metric_view(db: Dict[str, Any], metric_type: str) -> None:
    for line in metric_summary(db, metric_type):
        print(line)
    for line in render_value_wick_graph_10(entries_for_metric(db, metric_type), metric_type):
        print(line)


def print_overview(db: Dict[str, Any]) -> None:
    for metric in ["weight", "pulls", "pushes"]:
        print_metric_view(db, metric)
        print()


def print_recent(db: Dict[str, Any], n: int) -> None:
    es = recent_entries(db, n)
    if not es:
        print("(no entries)")
        return
    print(f"Last {len(es)} insertion(s):")
    for e in reversed(es):
        print(f"  id={e['id']}  day={entry_day(e)}  ts={e['ts']}  type={e['type']}  value={e['value']}")


def interactive_loop(db: Dict[str, Any], password: str) -> None:
    print("Unlocked. Type 'help' for commands.")

    while True:
        try:
            line = input("> ")
        except (EOFError, KeyboardInterrupt):
            print()
            break

        parts = parse_command(line)
        if not parts:
            continue

        cmd = parts[0].lower()

        try:
            if cmd in ("quit", "exit"):
                break

            if cmd == "help":
                print(HELP_TEXT)
                continue

            if cmd == "overview":
                print_overview(db)
                continue

            if cmd == "weight":
                print_metric_view(db, "weight")
                continue

            if cmd == "pulls":
                print_metric_view(db, "pulls")
                continue

            if cmd == "pushes":
                print_metric_view(db, "pushes")
                continue

            if cmd == "recent":
                n = 5
                if len(parts) >= 2:
                    n = int(parts[1])
                print_recent(db, n)
                continue

            if cmd == "delete":
                if len(parts) != 2:
                    print("Usage: delete <id>")
                    continue
                entry_id = parts[1]
                ok = delete_entry(db, entry_id)
                if not ok:
                    print("No entry found with that id.")
                    continue
                save_db_file(DB_FILE, password, db)
                print("Deleted.")
                print_recent(db, 5)
                continue

            if cmd in ("addweight", "addpulls", "addpushes"):
                # Accepted:
                #   <cmd> <value>
                #   <cmd> <value> silent
                #   <cmd> <value> YYYY-MM-DD
                #   <cmd> <value> YYYY-MM-DD silent
                if len(parts) < 2 or len(parts) > 4:
                    print(f"Usage: {cmd} <value> [YYYY-MM-DD] [silent]")
                    continue

                hashmap= {"addweight":"weight", "addpulls":"pulls", "addpushes":"pushes"}

                metric_type = hashmap[cmd]

                # parse value
                if metric_type == "weight":
                    value = float(parts[1])
                else:
                    value = int(parts[1])
                    if value < 0:
                        raise ValueError("Reps must be non-negative.")

                # parse remaining tokens
                rest = parts[2:]  # [], ["silent"], ["YYYY-MM-DD"], ["YYYY-MM-DD","silent"], ["silent","YYYY-MM-DD"]
                silent = False
                day = None

                if "silent" in rest:
                    silent = True
                    rest = [x for x in rest if x != "silent"]

                if len(rest) > 1:
                    print(f"Usage: {cmd} <value> [YYYY-MM-DD] [silent]")
                    continue
                if len(rest) == 1:
                    day = parse_day(rest[0])

                add_entry_one_per_day(db, metric_type, value, day=day)
                save_db_file(DB_FILE, password, db)

                if not silent:
                    print_metric_view(db, metric_type)
                continue

            print("Unknown command. Type 'help'.")

        except Exception as e:
            print(f"Error: {e}")


def main() -> None:
    password = require_password()

    try:
        db = load_db_file(DB_FILE, password, default_obj=new_db())
    except CryptoStoreError as e:
        raise SystemExit(str(e))

    interactive_loop(db, password)