import datetime as dt
import uuid
from typing import Any, Dict, List, Optional


DB_VERSION = 2


def new_db() -> Dict[str, Any]:
    return {"version": DB_VERSION, "entries": []}


def normalize_type(t: str) -> str:
    mapping = {
        "addweight": "weight",
        "addpulls": "pulls",
        "addpushes": "pushes",
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


def entry_day(e: Dict[str, Any]) -> dt.date:
    """Get the day this entry is for (not when it was inserted)."""
    if "day" in e:
        return dt.date.fromisoformat(e["day"])
    # Backward compat: derive from ts
    return parse_iso(e["ts"]).astimezone(dt.timezone.utc).date()


def entries_for_metric(db: Dict[str, Any], metric_type: str) -> List[Dict[str, Any]]:
    t = normalize_type(metric_type)
    es = [e for e in db["entries"] if e.get("type") == t]
    es.sort(key=lambda e: e["ts"])
    return es


def add_entry(
    db: Dict[str, Any],
    metric_type: str,
    value: float,
    day: Optional[dt.date] = None,
) -> Dict[str, Any]:
    """
    Add a new entry (append-only, no merging).

    Args:
        db: Database dict
        metric_type: "weight", "pulls", or "pushes"
        value: Numeric value
        day: Which date this stat is FOR (defaults to today)

    Returns the created entry.
    """
    t = normalize_type(metric_type)
    now = now_utc()
    target_day = day or now.date()

    entry = {
        "id": str(uuid.uuid4()),
        "day": target_day.isoformat(),
        "ts": now.isoformat(),
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


def entries_for_metric_by_day(db: Dict[str, Any], metric_type: str) -> List[Dict[str, Any]]:
    """
    Get aggregated entries for a metric, one per day.

    For each day with entries:
      - weight: average all values for that day
      - pulls/pushes: max of all values for that day

    Returns list of synthetic entries (one per day) sorted by day.
    Each entry has: {day, ts, type, value}
    """
    t = normalize_type(metric_type)
    es = [e for e in db["entries"] if e.get("type") == t]

    if not es:
        return []

    # Group by day
    by_day: Dict[str, List[Dict[str, Any]]] = {}
    for e in es:
        day_str = entry_day(e).isoformat()
        if day_str not in by_day:
            by_day[day_str] = []
        by_day[day_str].append(e)

    # Aggregate each day
    aggregated = []
    for day_str, day_entries in by_day.items():
        values = [float(e["value"]) for e in day_entries]

        if t == "weight":
            agg_value = sum(values) / len(values)  # average
        elif t in ("pulls", "pushes"):
            agg_value = max(values)  # max
        else:
            agg_value = values[-1]  # fallback: last value

        # Use the latest timestamp for this day as representative
        latest_ts = max(day_entries, key=lambda e: e["ts"])["ts"]

        aggregated.append({
            "day": day_str,
            "ts": latest_ts,
            "type": t,
            "value": agg_value,
        })

    # Sort by day
    aggregated.sort(key=lambda e: e["day"])
    return aggregated


def recent_entries(db: Dict[str, Any], n: int = 5) -> List[Dict[str, Any]]:
    """Get the most recent entries by insertion time (ts)."""
    es = list(db["entries"])
    es.sort(key=lambda e: (e["ts"], e["id"]))
    return es[-n:]