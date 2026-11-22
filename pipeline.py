"""Fit creative flights into audience calendars and daily delivery capacity."""

from collections import Counter, defaultdict
from datetime import date, timedelta
import hashlib

TITLE = "Campaign Flight Planner"
DESCRIPTION = "Schedule multi-day creative flights inside allowed windows and export approved placements to iCalendar."
PROMPT = "Explain schedule pressure using dates, audience conflicts and capacity evidence. Identify one concrete constraint to revisit for each unscheduled flight. Never imply impressions or spend have been booked."


def rows(data, key, limit=250, empty=False):
    value = data.get(key) if isinstance(data, dict) else None
    if not isinstance(value, list) or len(value) > limit or (not value and not empty):
        raise ValueError(
            f"{key} must be a list with {'0' if empty else '1'} to {limit} entries"
        )
    if any(not isinstance(entry, dict) for entry in value):
        raise ValueError(f"Every {key} entry must be an object")
    return value


def text(value, name, limit=200):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f"{name} must be nonblank text, at most {limit} characters")
    return value.strip()


def integer(value, name, lo=0, hi=1_000_000):
    if type(value) is not int or not lo <= value <= hi:
        raise ValueError(f"{name} must be an integer between {lo} and {hi}")
    return value


def selected(evidence, approved):
    by_id = {c["id"]: c for c in evidence["candidates"]}
    result = []
    seen = set()
    for item in approved:
        key = item.get("id") if isinstance(item, dict) else None
        if not isinstance(key, str) or key not in by_id or key in seen:
            raise ValueError("Unknown or duplicate approval")
        seen.add(key)
        result.append(by_id[key])
    return result


def day(value):
    if not isinstance(value, str):
        raise ValueError("Use ISO dates YYYY-MM-DD")
    try:
        d = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("Use ISO dates YYYY-MM-DD") from exc
    if value != d.isoformat() or not 2000 <= d.year <= 2100:
        raise ValueError("Use calendar dates from 2000 through 2100")
    return d


def prepare(data: dict) -> dict:
    if not isinstance(data, dict):
        raise ValueError("Expected an object")
    cap = integer(data.get("daily_capacity"), "daily_capacity", 1, 10000)
    load = Counter()
    aud = defaultdict(list)
    records = []
    candidates = []
    ids = set()
    queue = []

    def identity(f):
        key = text(f.get("id"), "flight id", 80)
        if key in ids:
            raise ValueError("Flight IDs must be unique")
        ids.add(key)
        return (
            key,
            text(f.get("audience"), "audience", 80),
            integer(f.get("units", 1), "units", 1, 10000),
        )

    def reserve(key, audience, units, start, length):
        for off in range(length):
            d = start + timedelta(days=off)
            load[d] += units
            aud[d, audience.casefold()].append(key)

    for f in rows(data, "booked", 150, empty=True):
        key, audience, units = identity(f)
        start = day(f.get("start"))
        length = integer(f.get("days"), "days", 1, 90)
        reserve(key, audience, units, start, length)
        records.append(
            {
                "id": "booked:" + key,
                "flight": key,
                "audience": audience,
                "units": units,
                "start": str(start),
                "end_exclusive": str(start + timedelta(days=length)),
                "status": "Booked",
            }
        )
    collisions = 0
    for (d, audience), bookings in sorted(aud.items()):
        if len(bookings) > 1:
            collisions += 1
            records.append(
                {
                    "id": f"audience-clash:{d}:{audience}",
                    "status": "Existing audience collision",
                    "date": str(d),
                    "audience": audience,
                    "flights": bookings[:],
                }
            )
    for d, v in sorted(load.items()):
        if v > cap:
            collisions += 1
            records.append(
                {
                    "id": "capacity-clash:" + str(d),
                    "status": "Existing capacity overage",
                    "date": str(d),
                    "units_booked": v,
                    "daily_capacity": cap,
                }
            )
    for f in rows(data, "flights", 150):
        key, audience, units = identity(f)
        start = day(f.get("earliest"))
        last = day(f.get("latest_end"))
        days = integer(f.get("days"), "days", 1, 90)
        priority = integer(f.get("priority", 3), "priority", 1, 5)
        span = (last - start).days + 1
        if not 1 <= span <= 366:
            raise ValueError("Each flight needs a window of 1–366 days")
        queue.append((-priority, span - days, start, key, audience, units, days, last))
    for _, slack, start, key, audience, units, length, last in sorted(queue):
        reason = Counter()
        first = None
        for shift in range(slack + 1):
            trial = start + timedelta(days=shift)
            dates = [trial + timedelta(days=i) for i in range(length)]
            if any(aud.get((d, audience.casefold())) for d in dates):
                reason["Audience overlap"] += 1
                continue
            if any(load[d] + units > cap for d in dates):
                reason["Daily capacity"] += 1
                continue
            first = trial
            break
        evidence = {
            "id": "request:" + key,
            "flight": key,
            "audience": audience,
            "window_start": str(start),
            "window_end": str(last),
            "duration_days": length,
            "units": units,
            "rejected_starts": dict(reason),
        }
        if first is None:
            evidence["status"] = (
                "Window shorter than flight" if slack < 0 else "No feasible start"
            )
        else:
            reserve(key, audience, units, first, length)
            end = first + timedelta(days=length)
            evidence.update(status="Proposed", start=str(first), end_exclusive=str(end))
            candidates.append(
                {
                    "id": "place:" + key,
                    "action": f"Schedule {key} for {first} through {end - timedelta(days=1)}",
                    "evidence_ids": [evidence["id"]],
                    "flight": key,
                    "audience": audience,
                    "units": units,
                    "start": str(first),
                    "end_exclusive": str(end),
                }
            )
        records.append(evidence)
    return {
        "summary": f"Placed {len(candidates)} of {len(queue)} requested flights; found {collisions} pre-existing calendar conflicts.",
        "metrics": {
            "Requested": len(queue),
            "Placed": len(candidates),
            "Existing conflicts": collisions,
        },
        "records": records,
        "candidates": candidates,
    }


def ical_text(s):
    return (
        s.replace("\\", "\\\\")
        .replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\n", "\\n")
        .replace(";", "\\;")
        .replace(",", "\\,")
    )


def folded(line):
    parts = [""]
    used = 0
    for char in line:
        size = len(char.encode("utf-8"))
        if used + size > 75:
            parts.append(" ")
            used = 1
        parts[-1] += char
        used += size
    return "\r\n".join(parts)


def export(data, evidence, approved):
    events = [r for r in evidence["records"] if r.get("status") == "Booked"] + selected(
        evidence, approved
    )
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Campaign Flight Planner//Reviewed Flights//EN",
        "CALSCALE:GREGORIAN",
    ]
    # Deterministic snapshot timestamp; this file does not perform a booking.
    stamp = (
        min(
            r["window_start"] for r in evidence["records"] if "window_start" in r
        ).replace("-", "")
        + "T000000Z"
    )
    for f in sorted(events, key=lambda x: (x["start"], x["flight"])):
        uid = (
            hashlib.sha256(f["flight"].encode()).hexdigest()[:24]
            + "@campaign-flight-planner.local"
        )
        lines.extend(
            [
                "BEGIN:VEVENT",
                "UID:" + uid,
                "DTSTAMP:" + stamp,
                "DTSTART;VALUE=DATE:" + f["start"].replace("-", ""),
                "DTEND;VALUE=DATE:" + f["end_exclusive"].replace("-", ""),
                "SUMMARY:" + ical_text(f["flight"]),
                "DESCRIPTION:"
                + ical_text(f"Audience: {f['audience']}. Daily units: {f['units']}."),
                "END:VEVENT",
            ]
        )
    lines.append("END:VCALENDAR")
    return {"creative-flights.ics": "\r\n".join(folded(l) for l in lines) + "\r\n"}
