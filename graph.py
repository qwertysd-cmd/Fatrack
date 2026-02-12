import datetime as dt
from typing import Any, Dict, List, Optional, Tuple

from db import normalize_type, parse_iso


GRAPH_BINS = 10
COL_WIDTH = 5
COL_GAP = 5
GRAPH_HEIGHT = 10
LEFT_MARGIN = 2


def _format_in_col(text: Optional[str], width: int) -> str:
    s = "" if text is None else str(text)
    if len(s) > width:
        s = s[-width:]
    pad = width - len(s)
    left = pad // 2
    right = pad - left
    return (" " * left) + s + (" " * right)


def bucketize_by_time(entries: List[Dict[str, Any]], bins: int) -> List[List[Dict[str, Any]]]:
    """
    Make `bins` ideal time centers across [t0..t1].
    Assign each entry to the nearest center.

    This avoids dense logging periods dominating x-axis space.
    """
    if not entries:
        return [[] for _ in range(bins)]

    es = sorted(entries, key=lambda e: e["ts"])
    t0 = parse_iso(es[0]["ts"]).timestamp()
    t1 = parse_iso(es[-1]["ts"]).timestamp()

    if t0 == t1:
        buckets = [[] for _ in range(bins)]
        buckets[-1] = es[:]
        return buckets

    centers = []
    for i in range(bins):
        frac = i / (bins - 1) if bins > 1 else 0.0
        centers.append(t0 + frac * (t1 - t0))

    buckets: List[List[Dict[str, Any]]] = [[] for _ in range(bins)]
    for e in es:
        te = parse_iso(e["ts"]).timestamp()
        best_i = 0
        best_d = abs(te - centers[0])
        for i in range(1, bins):
            d = abs(te - centers[i])
            if d < best_d:
                best_d = d
                best_i = i
        buckets[best_i].append(e)

    for b in buckets:
        b.sort(key=lambda e: e["ts"])
    return buckets


def summarize_bucket(bucket: List[Dict[str, Any]]) -> Optional[Tuple[float, dt.datetime]]:
    if not bucket:
        return None
    vals = [float(e["value"]) for e in bucket]
    avg_val = sum(vals) / len(vals)

    epochs = [parse_iso(e["ts"]).timestamp() for e in bucket]
    avg_epoch = sum(epochs) / len(epochs)
    avg_ts = dt.datetime.fromtimestamp(avg_epoch, tz=dt.timezone.utc)
    return avg_val, avg_ts


def render_value_wick_graph_10(entries: List[Dict[str, Any]], metric_type: str) -> List[str]:
    t = normalize_type(metric_type)
    is_weight = (t == "weight")
    unit = "kg" if is_weight else "reps"

    if not entries:
        return [f"{t} graph: (no data)"]

    es = sorted(entries, key=lambda e: e["ts"])
    now_dt = dt.datetime.now(dt.timezone.utc)

    buckets = bucketize_by_time(es, GRAPH_BINS)

    bins: List[Optional[Tuple[float, dt.datetime, int]]] = []
    for b in buckets:
        s = summarize_bucket(b)
        if s is None:
            bins.append(None)
        else:
            avg_val, avg_dt = s
            days_ago = int(round((now_dt - avg_dt).total_seconds() / 86400.0))
            bins.append((avg_val, avg_dt, days_ago))

    values = [x[0] for x in bins if x is not None]
    if not values:
        return [f"{t} graph: (no data)"]

    actual_min = min(values)
    actual_max = max(values)
    actual_range = actual_max - actual_min
    if actual_range == 0:
        actual_range = 1.0

    graph_max = actual_max
    graph_min = actual_min - 0.5 * actual_range
    graph_range = graph_max - graph_min

    def value_to_row(v: float) -> int:
        if v <= graph_min:
            return 0
        if v >= graph_max:
            return GRAPH_HEIGHT - 1
        pos = (v - graph_min) / graph_range
        r = int(round(pos * (GRAPH_HEIGHT - 1)))
        return max(0, min(GRAPH_HEIGHT - 1, r))

    col_rows: List[Optional[int]] = []
    col_val_text: List[Optional[str]] = []
    col_days_text: List[Optional[str]] = []

    for b in bins:
        if b is None:
            col_rows.append(None)
            col_val_text.append(None)
            col_days_text.append(None)
        else:
            v, _avg_dt, days_ago = b
            col_rows.append(value_to_row(v))
            if is_weight:
                col_val_text.append(f"{v:.2f}")
            else:
                col_val_text.append(str(int(round(v))))
            col_days_text.append(str(days_ago))

    lines: List[str] = []
    #lines.append(f"{t} graph (10 time-bins, avg per bin) [{unit}]")
    #lines.append(f"latest: {es[-1]['ts']}")
    #lines.append(f"actual range: {actual_min:.2f}..{actual_max:.2f}  graph range: {graph_min:.2f}..{graph_max:.2f}  (min extended)")

    for r in range(GRAPH_HEIGHT - 1, -1, -1):
        row = (" " * LEFT_MARGIN)
        for c in range(GRAPH_BINS):
            cell = [" "] * COL_WIDTH
            rr = col_rows[c]
            if rr is None:
                pass
            else:
                if r == rr:
                    cell = list(_format_in_col(col_val_text[c], COL_WIDTH))
                elif r < rr:
                    cell[COL_WIDTH // 2] = "|"
            row += "".join(cell) + (" " * COL_GAP)
        lines.append(row.rstrip())

    baseline = (" " * LEFT_MARGIN) + "-" * ((COL_WIDTH + COL_GAP) * GRAPH_BINS)
    lines.append(baseline.rstrip())

    xlab = (" " * LEFT_MARGIN)
    for c in range(GRAPH_BINS):
        xlab += _format_in_col(col_days_text[c], COL_WIDTH) + (" " * COL_GAP)
    lines.append(xlab.rstrip())

    lines.append((" " * LEFT_MARGIN) + "days ago")
    return lines
