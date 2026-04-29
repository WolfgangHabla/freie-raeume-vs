"""Sammle DHBW-VS-Räume aus mehreren Rapla-Wochen und pflege rooms.json.

Usage:
    python collect_rooms.py --weeks 12 --start 2026-04-20
    python collect_rooms.py --quarter 2026-Q2

Das Skript iteriert über mehrere aufeinanderfolgende Wochen, sammelt alle
Räume, die Rapla als Ressource ausgibt, und merged sie mit einer bestehenden
`rooms.json`. Manuelle Anpassungen an `rooms.json` (insbesondere das
`include`-Flag und manuell gesetzte Metadaten) bleiben beim Merge erhalten.

Ausgabe am Ende:
- Neue Räume (seit letztem Lauf hinzugekommen)
- Unbekannte Zellen-Samples (kein Raum erkannt) zur Kalibrierung
"""

import argparse
import json
import sys
import time
from datetime import date, timedelta
from pathlib import Path

from app import (
    parse_rapla_week_rooms,
    room_building,
    room_short_name,
)

ROOMS_JSON = Path(__file__).parent / "rooms.json"
RAUMLISTE_MD = Path(__file__).parent / "Raumliste.md"

QUARTER_MONTHS = {
    1: (1, 3),
    2: (4, 6),
    3: (7, 9),
    4: (10, 12),
}


def mondays_in_quarter(year, quarter):
    """Montage, deren Woche primär im Quartal liegt (ISO-Woche)."""
    first_month, last_month = QUARTER_MONTHS[quarter]
    d = date(year, first_month, 1)
    d -= timedelta(days=d.weekday())
    if last_month == 12:
        end = date(year, 12, 31)
    else:
        end = date(year, last_month + 1, 1) - timedelta(days=1)
    while d <= end:
        thursday = d + timedelta(days=3)
        if first_month <= thursday.month <= last_month and thursday.year == year:
            yield d
        d += timedelta(weeks=1)


def collect_rooms(mondays):
    """Iteriere Montage, sammle (raum_set, unknown_samples).

    Returns: (found_rooms: set[str], unknown_samples: list[str])
    """
    found = set()
    unknown = []
    for i, monday in enumerate(mondays):
        print(f"  [{i+1}/{len(mondays)}] KW{monday.isocalendar()[1]} ({monday}) ...",
              end=" ", flush=True)
        try:
            result = parse_rapla_week_rooms(monday.day, monday.month, monday.year)
        except Exception as e:
            print(f"FEHLER: {e}")
            continue
        if result is None:
            print("kein Inhalt")
            continue
        week_rooms = set()
        for day in result["days"]:
            for ev in day["events"]:
                for r in ev["rooms"]:
                    week_rooms.add(r)
        found |= week_rooms
        for sample in result.get("_unknown_cells", []):
            if sample not in unknown and len(unknown) < 20:
                unknown.append(sample)
        print(f"{len(week_rooms)} Räume, {len(result['days'])} Tage")
        if i < len(mondays) - 1:
            time.sleep(2)
    return found, unknown


def load_existing(path):
    if not path.exists():
        return {"rooms": [], "last_collected": None, "sources_weeks": 0}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        print(f"Warnung: {path} konnte nicht gelesen werden ({e}), neu erstellt.")
        return {"rooms": [], "last_collected": None, "sources_weeks": 0}


def merge_rooms(existing, found_names):
    """Merge new room names into existing rooms.json data structure.

    - Neue Räume werden mit sinnvollen Defaults eingefügt.
    - Bestehende Räume behalten alle manuell gesetzten Felder (include,
      building, floor, etc.).
    - Räume, die NICHT mehr gefunden wurden, bleiben in der Liste erhalten
      (nur Diff-Meldung).
    """
    existing_by_name = {r["name"]: r for r in existing.get("rooms", [])}
    new_names = sorted(found_names - set(existing_by_name.keys()))
    removed_names = sorted(set(existing_by_name.keys()) - found_names)

    for name in new_names:
        short = room_short_name(name)
        building = room_building(name)
        # Etage aus short_name extrahieren: "C 3.24" → floor 3, "D 108" → floor 1
        floor = None
        if short:
            parts = short.split()
            if len(parts) == 2:
                num = parts[1].lstrip("-")
                if "." in num:
                    try:
                        floor = int(num.split(".")[0])
                    except ValueError:
                        floor = None
                elif num.isdigit() and len(num) == 3:
                    # "108" → floor 1, "014" → floor 0
                    try:
                        floor = int(num[0])
                    except ValueError:
                        floor = None
        existing_by_name[name] = {
            "name": name,
            "short_name": short,
            "building": building,
            "floor": floor,
            "include": True,
        }

    # Sortieren nach name
    merged = sorted(existing_by_name.values(), key=lambda r: r["name"])
    return merged, new_names, removed_names


def save_rooms(path, rooms, weeks_count):
    data = {
        "rooms": rooms,
        "last_collected": date.today().isoformat(),
        "sources_weeks": weeks_count,
    }
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def write_raumliste(path, rooms):
    """Schreibe eine menschenlesbare Referenz-Raumliste als Markdown.

    Gruppiert nach Gebäude (A, B, C, ...), innerhalb jeder Gruppe nach
    kanonischem Namen sortiert. Lexikographische Sortierung stellt
    "C -1.21" korrekt vor "C 1.20" (weil "-" < "1" in ASCII).
    Räume mit include=False werden ausgeblendet.
    """
    by_building = {}
    for r in rooms:
        if not r.get("include", True):
            continue
        b = r.get("building") or "?"
        by_building.setdefault(b, []).append(r)

    lines = ["# DHBW-VS Raumliste", ""]
    lines.append(
        f"Automatisch erzeugt von `collect_rooms.py` "
        f"am {date.today().isoformat()}."
    )
    total = sum(len(v) for v in by_building.values())
    lines.append(f"Quelle: {total} Räume aus Rapla.")
    lines.append("")

    for building in sorted(by_building.keys()):
        lines.append(f"## Gebäude {building}")
        lines.append("")
        for r in sorted(by_building[building], key=lambda x: x["name"]):
            short = r.get("short_name") or ""
            name = r["name"]
            if short and name.startswith(short):
                rest = name[len(short):].strip()
                if rest:
                    lines.append(f"- **{short}** — {rest}")
                else:
                    lines.append(f"- **{short}**")
            else:
                lines.append(f"- {name}")
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="DHBW-VS-Räume aus Rapla sammeln.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--quarter", help="Quartal im Format YYYY-QN, z.B. 2026-Q2")
    group.add_argument("--weeks", type=int, help="Anzahl Wochen ab --start")
    parser.add_argument("--start", help="Start-Montag (ISO, z.B. 2026-04-20). "
                                        "Nur mit --weeks.")
    args = parser.parse_args()

    if args.quarter:
        try:
            y_str, q_str = args.quarter.split("-Q")
            year = int(y_str)
            q = int(q_str)
        except (ValueError, IndexError):
            print("Fehler: Quartal im Format YYYY-QN (z.B. 2026-Q2)")
            sys.exit(1)
        mondays = list(mondays_in_quarter(year, q))
        print(f"Quartal {args.quarter}: {len(mondays)} Wochen")
    else:
        if not args.start:
            print("Fehler: --start erforderlich mit --weeks")
            sys.exit(1)
        try:
            start = date.fromisoformat(args.start)
        except ValueError:
            print("Fehler: --start muss ISO-Datum sein (YYYY-MM-DD)")
            sys.exit(1)
        start -= timedelta(days=start.weekday())  # auf Montag zurück
        mondays = [start + timedelta(weeks=i) for i in range(args.weeks)]
        print(f"{len(mondays)} Wochen ab {start}")

    found, unknown = collect_rooms(mondays)

    existing = load_existing(ROOMS_JSON)
    merged, new_names, removed_names = merge_rooms(existing, found)
    save_rooms(ROOMS_JSON, merged, len(mondays))
    write_raumliste(RAUMLISTE_MD, merged)

    print()
    print("=" * 60)
    print(f"Gesamt: {len(merged)} Räume in {ROOMS_JSON.name}")
    print(f"Referenz-Raumliste: {RAUMLISTE_MD.name}")
    print(f"  Neu gefunden: {len(new_names)}")
    for n in new_names:
        print(f"    + {n}")
    if removed_names:
        print(f"  Nicht mehr gesehen: {len(removed_names)}")
        for n in removed_names:
            print(f"    - {n}")

    if unknown:
        print()
        print("=" * 60)
        print("Zellen ohne erkannten Raum (zur Kalibrierung prüfen):")
        for u in unknown:
            print(f"  ??? {u[:200]}")

    print()
    print(f"Tipp: rooms.json manuell prüfen. Falsche Räume mit "
          f"'include': false markieren.")


if __name__ == "__main__":
    main()
