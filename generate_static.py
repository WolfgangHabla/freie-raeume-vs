"""Generiere eine statische HTML-Übersicht freier Räume an der DHBW VS.

Usage:
    python generate_static.py --quarter 2026-Q2 --output docs/index.html
    python generate_static.py --weeks 12 --start 2026-04-20 --output docs/index.html
    python generate_static.py --refresh-week --output docs/index.html

Das Skript iteriert alle Wochen eines Quartals, ruft für jede Woche die
Rapla-Daten ab, berechnet die freien Zeitfenster pro Raum und Tag und erzeugt
eine eigenständige HTML-Datei mit eingebettetem JSON. Keine Server-Abfragen
im Browser nötig.

`--refresh-week` ist ein Schnellmodus für häufige Updates (z.B. alle 15 Min):
Er lädt den kompletten Datenbestand von der aktuell live deployten Seite
(`--source-url`) statt vom halben Quartal, ersetzt darin nur die aktuelle
Woche mit frisch von Rapla geholten Daten und schreibt das Ergebnis zurück.
So kostet ein Schnell-Refresh nur 1 Rapla-Anfrage statt ~13.
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

from app import (
    _holidays_bw,
    build_day_free_rooms,
    parse_rapla_week_rooms,
)

ROOMS_JSON = Path(__file__).parent / "rooms.json"
DEFAULT_SOURCE_URL = "https://wolfganghabla.github.io/freie-raeume-vs/"


def now_berlin():
    return datetime.now(ZoneInfo("Europe/Berlin"))

QUARTER_MONTHS = {
    1: ("Januar\u2013M\u00e4rz", 1, 3),
    2: ("April\u2013Juni", 4, 6),
    3: ("Juli\u2013September", 7, 9),
    4: ("Oktober\u2013Dezember", 10, 12),
}


def mondays_in_quarter(year, quarter):
    _, first_month, last_month = QUARTER_MONTHS[quarter]
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


def load_rooms():
    """Lädt rooms.json und gibt nur die eingeschlossenen Räume zurück."""
    if not ROOMS_JSON.exists():
        print(f"Fehler: {ROOMS_JSON} fehlt. Bitte zuerst collect_rooms.py ausführen.")
        sys.exit(1)
    data = json.loads(ROOMS_JSON.read_text(encoding="utf-8"))
    return [r for r in data.get("rooms", []) if r.get("include", True)]


def build_week_data(monday, rooms_meta):
    """Hole eine Woche von Rapla und berechne freie Slots pro Raum und Tag.

    Rückgabe: {
      "monday": "2026-04-20",
      "week_label": "KW 17",
      "days": [
        {
          "label": "Mo 20.04.",
          "date": "2026-04-20",
          "weekday": 0,
          "is_holiday": False,
          "rooms": {
            "C 3.24 Hörsaal (Sozialwesen)": {"status": "partial", "free": [[480,540],...]},
            ...
          }
        }, ...
      ]
    }
    """
    day, month, year = monday.day, monday.month, monday.year
    room_names = [r["name"] for r in rooms_meta]

    try:
        result = parse_rapla_week_rooms(day, month, year)
    except Exception as e:
        print(f"FEHLER: {e}")
        result = None

    holidays = _holidays_bw(year)
    days_out = []

    if result is None:
        # Trotzdem 5+1 Tage ausgeben (alle als "frei"/"Feiertag")
        for i in range(6):
            d = monday + timedelta(days=i)
            is_holiday = d in holidays
            day_abbr = ["Mo", "Di", "Mi", "Do", "Fr", "Sa"][i]
            label = f"{day_abbr} {d.strftime('%d.%m.')}"
            rooms_for_day = build_day_free_rooms(
                [], room_names, d, is_holiday,
            )
            days_out.append({
                "label": label,
                "date": d.isoformat(),
                "weekday": i,
                "is_holiday": is_holiday,
                "rooms": rooms_for_day,
            })
        return {
            "monday": monday.isoformat(),
            "week_label": f"KW {monday.isocalendar()[1]}",
            "days": days_out,
            "error": "Parser lieferte None",
        }

    # Map day-label → day data aus parser-Result
    for i, day_entry in enumerate(result["days"]):
        d = date.fromisoformat(day_entry["date"])
        rooms_for_day = build_day_free_rooms(
            day_entry["events"],
            room_names,
            d,
            day_entry["is_holiday"],
        )
        days_out.append({
            "label": day_entry["label"],
            "date": day_entry["date"],
            "weekday": d.weekday(),
            "is_holiday": day_entry["is_holiday"],
            "rooms": rooms_for_day,
        })

    return {
        "monday": monday.isoformat(),
        "week_label": result.get("week", f"KW {monday.isocalendar()[1]}"),
        "days": days_out,
    }


HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="de">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Freie Räume DHBW VS — {title}</title>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            max-width: 960px;
            margin: 2rem auto;
            padding: 0 1rem;
            color: #333;
        }}
        h1 {{
            font-size: 1.4rem;
            margin-bottom: 0.25rem;
            color: #1a1a1a;
        }}
        .subtitle {{
            font-size: 0.9rem;
            color: #6b7280;
            margin-bottom: 1.5rem;
        }}
        .controls {{
            position: sticky;
            top: 0;
            background: white;
            padding: 0.8rem 0;
            border-bottom: 1px solid #e5e7eb;
            margin-bottom: 1rem;
            z-index: 10;
            display: flex;
            gap: 1rem;
            flex-wrap: wrap;
            align-items: center;
        }}
        .controls label {{
            font-size: 0.9rem;
            color: #374151;
        }}
        .controls select {{
            padding: 0.4rem 0.6rem;
            border: 1px solid #ccc;
            border-radius: 4px;
            font-size: 0.95rem;
            margin-left: 0.3rem;
        }}
        #day-info {{
            font-size: 0.85rem;
            color: #6b7280;
            margin-left: auto;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 0.9rem;
        }}
        th, td {{
            padding: 0.55rem 0.6rem;
            text-align: left;
            border-bottom: 1px solid #e5e7eb;
            vertical-align: top;
        }}
        th {{
            background: #f9fafb;
            font-weight: 600;
            font-size: 0.85rem;
            text-transform: uppercase;
            letter-spacing: 0.03em;
            color: #374151;
        }}
        tr:hover td {{ background: #f9fafb; }}
        .room-name {{
            font-variant-numeric: tabular-nums;
            white-space: nowrap;
        }}
        .room-short {{
            font-weight: 600;
            color: #111827;
        }}
        .room-desc {{
            display: block;
            font-size: 0.75rem;
            color: #9ca3af;
            font-weight: normal;
        }}
        .chip {{
            display: inline-block;
            padding: 0.15rem 0.5rem;
            border-radius: 999px;
            font-size: 0.82rem;
            font-variant-numeric: tabular-nums;
            margin: 0.1rem 0.15rem 0.1rem 0;
            background: #f3f4f6;
            color: #374151;
        }}
        .chip-free {{ background: #ecfdf5; color: #047857; }}
        .chip-all-free {{ background: #d1fae5; color: #065f46; font-weight: 600; }}
        .chip-busy {{ background: #f3f4f6; color: #9ca3af; }}
        .chip-holiday {{ background: #f3f4f6; color: #9ca3af; font-style: italic; }}
        .building-sep td {{
            background: #f3f4f6;
            padding: 0.35rem 0.6rem;
            font-size: 0.75rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: #6b7280;
            font-weight: 600;
        }}
        .generated {{
            margin-top: 2rem;
            padding-top: 1rem;
            border-top: 1px solid #e5e7eb;
            font-size: 0.75rem;
            color: #9ca3af;
        }}
    </style>
</head>
<body>
    <h1>Freie Räume DHBW Villingen-Schwenningen</h1>
    <p class="subtitle">{title} — Übersicht zu welchen Uhrzeiten welche Räume frei sind (Betrachtungszeitraum 08:00–20:00)</p>

    <div class="controls">
        <label>Woche: <select id="week-select"></select></label>
        <label>Tag: <select id="day-select"></select></label>
        <span id="day-info"></span>
    </div>

    <table id="rooms-table">
        <thead>
            <tr>
                <th style="width: 30%">Raum</th>
                <th>Freie Zeiten</th>
            </tr>
        </thead>
        <tbody id="rooms-body"></tbody>
    </table>

    <p class="generated">Generiert am {generated}. Datenquelle: DHBW Rapla. Raumliste aus rooms.json.</p>

    <script>
    const DATA = {data_json};
    const ROOMS_META = {rooms_json};

    const weekSelect = document.getElementById('week-select');
    const daySelect = document.getElementById('day-select');
    const body = document.getElementById('rooms-body');
    const dayInfo = document.getElementById('day-info');

    // Wochen-Dropdown befüllen
    DATA.forEach((week, idx) => {{
        const opt = document.createElement('option');
        opt.value = idx;
        opt.textContent = week.week_label + ' (' + week.monday + ')';
        weekSelect.appendChild(opt);
    }});

    // Default-Index: heutige Woche, falls verfügbar
    function pickDefaultWeek() {{
        const today = new Date().toISOString().slice(0, 10);
        for (let i = 0; i < DATA.length; i++) {{
            const end = new Date(DATA[i].monday);
            end.setDate(end.getDate() + 6);
            if (today <= end.toISOString().slice(0, 10)) return i;
        }}
        return 0;
    }}

    function formatMinutes(m) {{
        const h = Math.floor(m / 60);
        const mm = m % 60;
        return h.toString().padStart(2, '0') + ':' + mm.toString().padStart(2, '0');
    }}

    function chipForRoom(roomStatus) {{
        if (!roomStatus) return '<span class="chip chip-busy">–</span>';
        if (roomStatus.status === 'holiday') {{
            return '<span class="chip chip-holiday">Feiertag</span>';
        }}
        if (roomStatus.status === 'free_all_day') {{
            return '<span class="chip chip-all-free">ganztägig frei</span>';
        }}
        if (roomStatus.status === 'busy_all_day') {{
            return '<span class="chip chip-busy">ganztägig belegt</span>';
        }}
        // partial
        return roomStatus.free.map(slot =>
            '<span class="chip chip-free">' +
            formatMinutes(slot[0]) + '–' + formatMinutes(slot[1]) +
            '</span>'
        ).join('');
    }}

    function render() {{
        const wIdx = parseInt(weekSelect.value, 10);
        const dIdx = parseInt(daySelect.value, 10);
        const week = DATA[wIdx];
        const day = week.days[dIdx];

        if (!day) {{
            body.innerHTML = '<tr><td colspan="2">Keine Daten für diesen Tag.</td></tr>';
            dayInfo.textContent = '';
            return;
        }}

        let info = day.label;
        if (day.is_holiday) info += ' · Feiertag';
        dayInfo.textContent = info;

        let html = '';
        let currentBuilding = null;
        for (const rm of ROOMS_META) {{
            if (rm.building !== currentBuilding) {{
                currentBuilding = rm.building;
                html += '<tr class="building-sep"><td colspan="2">Gebäude ' +
                        (currentBuilding || '(ohne)') + '</td></tr>';
            }}
            const status = day.rooms[rm.name];
            html += '<tr>' +
                '<td class="room-name">' +
                  '<span class="room-short">' + (rm.short_name || rm.name) + '</span>' +
                  '<span class="room-desc">' + rm.name + '</span>' +
                '</td>' +
                '<td>' + chipForRoom(status) + '</td>' +
                '</tr>';
        }}
        body.innerHTML = html;
    }}

    function populateDayDropdown(weekIdx) {{
        daySelect.innerHTML = '';
        DATA[weekIdx].days.forEach((day, i) => {{
            const opt = document.createElement('option');
            opt.value = i;
            opt.textContent = day.label;
            daySelect.appendChild(opt);
        }});
    }}

    // Initialisierung
    const defaultWeek = pickDefaultWeek();
    weekSelect.value = defaultWeek;
    populateDayDropdown(defaultWeek);
    // Default-Tag: heute falls enthalten, sonst Montag
    const todayStr = new Date().toISOString().slice(0, 10);
    let defaultDay = 0;
    DATA[defaultWeek].days.forEach((d, i) => {{
        if (d.date === todayStr) defaultDay = i;
    }});
    daySelect.value = defaultDay;
    render();

    weekSelect.addEventListener('change', () => {{
        populateDayDropdown(parseInt(weekSelect.value, 10));
        daySelect.value = 0;
        render();
    }});
    daySelect.addEventListener('change', render);
    </script>
</body>
</html>
"""


def generate(weeks_iter, title, output_path):
    rooms_meta = load_rooms()
    print(f"Geladen: {len(rooms_meta)} Räume aus rooms.json")

    all_weeks = []
    mondays = list(weeks_iter)
    for i, monday in enumerate(mondays):
        kw = monday.isocalendar()[1]
        print(f"  [{i+1}/{len(mondays)}] KW{kw} ({monday}) ...", end=" ", flush=True)
        data = build_week_data(monday, rooms_meta)
        all_weeks.append(data)
        print("OK")
        if i < len(mondays) - 1:
            time.sleep(2)

    html = HTML_TEMPLATE.format(
        title=title,
        generated=now_berlin().strftime("%d.%m.%Y %H:%M"),
        data_json=json.dumps(all_weeks, ensure_ascii=False),
        rooms_json=json.dumps(rooms_meta, ensure_ascii=False),
    )

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"\nFertig: {output_path} ({len(html)} Bytes)")


def fetch_existing_data(url):
    """Lädt die aktuell live deployte Seite und extrahiert Titel + Wochendaten.

    Rückgabe: (title, all_weeks) oder None, falls die Seite nicht erreichbar
    ist oder das erwartete Muster nicht gefunden wird (z.B. beim allerersten
    Deploy, wenn noch keine Seite existiert).
    """
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        print(f"Warnung: konnte {url} nicht laden ({e})")
        return None

    html = resp.text
    # Anker auf die nächste bekannte Zeile statt auf "];" — robuster, falls
    # ein Raum-/Kursname zufällig diese Zeichenfolge enthält.
    data_m = re.search(r"const DATA = (.*?);\s*const ROOMS_META", html, re.S)
    title_m = re.search(r'<p class="subtitle">(.*?) — Übersicht', html, re.S)
    if not data_m:
        print(f"Warnung: konnte DATA nicht aus {url} extrahieren")
        return None

    all_weeks = json.loads(data_m.group(1))
    title = title_m.group(1).strip() if title_m else "Freie Räume"
    return title, all_weeks


def current_quarter_title_and_weeks(today):
    q = (today.month - 1) // 3 + 1
    label, _, _ = QUARTER_MONTHS[q]
    title = f"Q{q} {today.year} ({label})"
    return title, mondays_in_quarter(today.year, q)


def refresh_current_week(source_url, output_path):
    """Schneller Refresh: nur die aktuelle Woche neu von Rapla holen.

    Lädt den Bestand von der Live-Seite, ersetzt darin die aktuelle Woche
    und schreibt das Ergebnis zurück — kostet nur 1 Rapla-Anfrage statt
    einer vollen Quartalsgenerierung (~13 Anfragen).
    """
    rooms_meta = load_rooms()
    print(f"Geladen: {len(rooms_meta)} Räume aus rooms.json")

    existing = fetch_existing_data(source_url)
    today = now_berlin().date()

    if existing is None:
        print("Kein Bestand ladbar — fülle stattdessen das komplette aktuelle Quartal.")
        title, weeks_iter = current_quarter_title_and_weeks(today)
        generate(weeks_iter, title, output_path)
        return

    title, all_weeks = existing
    monday = today - timedelta(days=today.weekday())
    kw = monday.isocalendar()[1]
    print(f"Schnell-Refresh: nur KW{kw} ({monday})")

    fresh_week = build_week_data(monday, rooms_meta)

    monday_str = monday.isoformat()
    for i, w in enumerate(all_weeks):
        if w.get("monday") == monday_str:
            all_weeks[i] = fresh_week
            break
    else:
        all_weeks.append(fresh_week)
        all_weeks.sort(key=lambda w: w["monday"])

    html = HTML_TEMPLATE.format(
        title=title,
        generated=now_berlin().strftime("%d.%m.%Y %H:%M"),
        data_json=json.dumps(all_weeks, ensure_ascii=False),
        rooms_json=json.dumps(rooms_meta, ensure_ascii=False),
    )

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"\nFertig (Schnell-Refresh): {output_path} ({len(html)} Bytes)")


def main():
    parser = argparse.ArgumentParser(
        description="Statische Freie-Räume-Seite generieren"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--quarter", help="Quartal im Format YYYY-QN, z.B. 2026-Q2")
    group.add_argument("--weeks", type=int, help="Anzahl Wochen ab --start")
    group.add_argument(
        "--refresh-week", action="store_true",
        help="Nur aktuelle Woche aktualisieren (lädt Bestand von --source-url)",
    )
    parser.add_argument("--start", help="Start-Montag (ISO). Nur mit --weeks.")
    parser.add_argument(
        "--output", default="docs/index.html",
        help="Ausgabedatei (Standard: docs/index.html)",
    )
    parser.add_argument(
        "--source-url", default=DEFAULT_SOURCE_URL,
        help="Live-URL zum Nachladen des Bestands bei --refresh-week",
    )
    args = parser.parse_args()

    if args.refresh_week:
        refresh_current_week(args.source_url, args.output)
        return

    if args.quarter:
        try:
            y_str, q_str = args.quarter.split("-Q")
            year = int(y_str)
            q = int(q_str)
        except (ValueError, IndexError):
            print("Fehler: Quartal im Format YYYY-QN (z.B. 2026-Q2)")
            sys.exit(1)
        label, _, _ = QUARTER_MONTHS[q]
        title = f"Q{q} {year} ({label})"
        weeks_iter = mondays_in_quarter(year, q)
    else:
        if not args.start:
            print("Fehler: --start erforderlich mit --weeks")
            sys.exit(1)
        try:
            start = date.fromisoformat(args.start)
        except ValueError:
            print("Fehler: --start muss ISO-Datum sein")
            sys.exit(1)
        start -= timedelta(days=start.weekday())
        weeks_iter = (start + timedelta(weeks=i) for i in range(args.weeks))
        title = f"{args.weeks} Wochen ab {start}"

    generate(weeks_iter, title, args.output)


if __name__ == "__main__":
    main()
