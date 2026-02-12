import datetime as dt
import uuid
from typing import Any, Dict, List, Optional


DB_VERSION = 1


def new_db() -> Dict[str, Any]:
    return {"version": DB_VERSION, "entries": []}


def normalize_type(t: str) -> str:
    mapping = {
        "addweight": "weight",
        "weight": "weight",
        "pulls": "pulls",
        "pushes": "pushes",
    }
    if t not in mapping:
        raise ValueError(f"Unknown metric type: {t}")
    return mapping[t]


def parse_iso(ts: str) -> dt.datetime:
    return dt.datetime.fromisoformat(ts)


def now_utc() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def parse_day(s: str) -> dt.date:
    # strict YYYY-MM-DD
    if s.startswith("[") or s.endswith("]"):
        raise ValueError("Date must be YYYY-MM-DD (no brackets). Example: addweight 70.2 2026-01-21")
    return dt.date.fromisoformat(s)


def date_to_entry_ts(day: dt.date) -> str:
    # canonical timestamp for "a day"
    return dt.datetime(day.year, day.month, day.day, 12, 0, 0, tzinfo=dt.timezone.utc).isoformat()


def entry_day(e: Dict[str, Any]) -> dt.date:
    return parse_iso(e["ts"]).astimezone(dt.timezone.utc).date()


def entries_for_metric(db: Dict[str, Any], metric_type: str) -> List[Dict[str, Any]]:
    t = normalize_type(metric_type)
    es = [e for e in db["entries"] if e.get("type") == t]
    es.sort(key=lambda e: e["ts"])
    return es


def _find_entry_for_day(db: Dict[str, Any], metric_type: str, day: dt.date) -> Optional[Dict[str, Any]]:
    t = normalize_type(metric_type)
    for e in db["entries"]:
        if e.get("type") == t and entry_day(e) == day:
            return e
    return None


def has_entry_for_day(db: Dict[str, Any], metric_type: str, day: dt.date) -> bool:
    return _find_entry_for_day(db, metric_type, day) is not None


def add_entry_one_per_day(
    db: Dict[str, Any],
    metric_type: str,
    value: float,
    day: Optional[dt.date] = None,
) -> Dict[str, Any]:
    """
    Upsert semantics (one entry per metric per day):
      - weight: if exists, update value to avg(old, new)
      - pulls/pushes: if exists, update value to max(old, new)
      - if not exists, create a new entry

    Returns the created/updated entry.
    """
    t = normalize_type(metric_type)
    day = day or now_utc().date()

    existing = _find_entry_for_day(db, t, day)
    if existing is not None:
        old_val = float(existing["value"])
        new_val = float(value)

        if t == "weight":
            merged = (old_val + new_val) / 2.0
        elif t in ("pulls", "pushes"):
            merged = max(old_val, new_val)
        else:
            # Shouldn't happen due to normalize_type, but keep safe behavior.
            merged = new_val

        existing["value"] = merged
        # Keep the canonical ts for that day (no change) and stable id (no change).
        db["entries"].sort(key=lambda e: (e["ts"], e["id"]))
        return existing

    entry = {
        "id": str(uuid.uuid4()),
        "ts": date_to_entry_ts(day),
        "type": t,
        "value": value,
    }
    db["entries"].append(entry)
    db["entries"].sort(key=lambda e: (e["ts"], e["id"]))
    return entry


def delete_entry(db: Dict[str, Any], entry_id: str) -> bool:
    before = len(db["entries"])
    db["entries"] = [e for e in db["entries"] if e.get("id") != entry_id]
    return len(db["entries"]) != before


def recent_entries(db: Dict[str, Any], n: int = 5) -> List[Dict[str, Any]]:
    es = list(db["entries"])
    es.sort(key=lambda e: (e["ts"], e["id"]))
    return es[-n:]