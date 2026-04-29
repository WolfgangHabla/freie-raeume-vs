"""Freie-Räume-App — Rapla-Parser mit Raumextraktion und Slot-Berechnung.

Diese App ist eine eigenständige Schwester-App zu ../rapla-counter/. Die Helfer
(_easter_sunday, _holidays_bw, time_to_minutes, RAPLA_BASE, TIME_RE) sowie das
Gerüst des Rapla-Parsers wurden aus rapla-counter/app.py kopiert statt
importiert, damit die beiden Apps unabhängig voneinander versioniert und
verschoben werden können.

Beobachtete HTML-Struktur eines Rapla week_block (ermittelt am 2026-04-10
über Phase-0-Inspektion — siehe details.md):

    <td class="week_block" rowspan="9" style="...">
        <a href="#327">
            08:00 - 10:15<br>
            Kursname + Dozent
        </a>
        <br>
        <span class="resource">VS-SXX24H</span>          <!-- Kursgruppe -->
        <br>
        <span class="resource">C 2.21 Hörsaal (Sozialwesen)</span>  <!-- Raum -->
    </td>

Alle Teilnehmer, Kursgruppen und Räume sind als <span class="resource">
markiert und nicht typisiert. Die Unterscheidung erfolgt per Heuristik:
- Einträge, die mit "VS-" oder "VS " beginnen → Kursgruppen/Studierende
- Einträge mit Präfix "Buchstabe[ -]Ziffer" → Räume (z.B. "C 3.24", "D 108")
- Räume im UG haben Minus: "C -1.23 Gutenberg Tiefenhörsaal (Sozialwesen)"

Der kanonische Raumschlüssel ist der **komplette Rapla-Text** (inklusive
Beschreibung in Klammern), weil das der einzige stabile Bezeichner ist.
Ein zusätzlicher `short_name` ("C 3.24") wird heuristisch extrahiert und in
rooms.json gespeichert, um die Anzeige kompakter zu machen.
"""

import re
from datetime import date, timedelta

import requests
from bs4 import BeautifulSoup

RAPLA_BASE = (
    "https://rapla.dhbw.de/rapla/calendar?"
    "key=3m0O8EVJ2EaIYRGKNLrg04l51NVqdHUdqmVlRsPBk79i5RvkbUkRU3mkHJcmcGYy"
    "2iSBBS-IDTcajBP0hVZOvO4-EMZYgpSc7lj1FTS_4NLq5fb-ZVXqOA_7GxQZsYWjLmdX"
    "fLQ4PL68OAjCUe1vG-3T23NxGXJBNLjWKQqDU1o"
    "&salt=-888929980"
)

TIME_RE = re.compile(r"(\d{2}:\d{2})\s*-\s*(\d{2}:\d{2})")

# Heuristik für DHBW-VS-Raumnamen.
# Beispiele (beobachtet in Rapla, KW 17/2026):
#   "C 3.24 Hörsaal (Sozialwesen)"
#   "D 108 Hörsaal (CC)"
#   "B 201 Hörsaal (IB)"
#   "C -1.23 Gutenberg Tiefenhörsaal (Sozialwesen)"
#   "D 014 Hörsaal (Bank) (auch als PC-Raum nutzbar)"
# Präfix-Muster: Einzelbuchstabe + Leerzeichen + optional Minus + Ziffern(+Dezimal).
ROOM_PREFIX_RE = re.compile(r"^[A-Z]\s-?\d+(?:\.\d+)?(?:\s|$)")

# Short-Name aus dem vollen Raumnamen extrahieren (z.B. "C 3.24" aus
# "C 3.24 Hörsaal (Sozialwesen)").
ROOM_SHORT_RE = re.compile(r"^([A-Z]\s-?\d+(?:\.\d+)?)")

# Sonderräume, die nicht dem Muster entsprechen, aber als Raum zählen.
SPECIAL_ROOMS = {"Aula", "Mensa"}


def _easter_sunday(year):
    """Ostersonntag nach dem Anonymous-Gregorian-Algorithmus."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def _holidays_bw(year):
    """Gesetzliche Feiertage in Baden-Württemberg für ein Jahr."""
    easter = _easter_sunday(year)
    return {
        date(year, 1, 1),       # Neujahr
        date(year, 1, 6),       # Heilige Drei Könige
        easter + timedelta(-2), # Karfreitag
        easter + timedelta(1),  # Ostermontag
        date(year, 5, 1),       # Tag der Arbeit
        easter + timedelta(39), # Christi Himmelfahrt
        easter + timedelta(50), # Pfingstmontag
        easter + timedelta(60), # Fronleichnam
        date(year, 10, 3),      # Tag der Deutschen Einheit
        date(year, 11, 1),      # Allerheiligen
        date(year, 12, 25),     # 1. Weihnachtstag
        date(year, 12, 26),     # 2. Weihnachtstag
    }


def time_to_minutes(t):
    h, m = t.split(":")
    return int(h) * 60 + int(m)


def _is_room_name(text):
    """Heuristik: Ist der Text ein plausibler DHBW-VS-Raumname?"""
    text = text.strip()
    if not text:
        return False
    # Kursgruppen/Studierende beginnen mit "VS-" oder "VS "
    if text.startswith("VS-") or text.startswith("VS "):
        return False
    if text in SPECIAL_ROOMS:
        return True
    # Präfix prüfen: "C 3.24 ..." oder "D 108 ..." oder "C -1.23 ..."
    return bool(ROOM_PREFIX_RE.match(text))


def room_short_name(full_name):
    """Extrahiere den kurzen Code (z.B. 'C 3.24') aus einem vollen Raumnamen."""
    m = ROOM_SHORT_RE.match(full_name.strip())
    return m.group(1) if m else full_name.strip()


def room_building(full_name):
    """Extrahiere das Gebäude (ersten Buchstaben) aus einem Raumnamen."""
    full_name = full_name.strip()
    if full_name and full_name[0].isalpha():
        return full_name[0]
    return None


# Rapla hängt an Raumnamen gern Fachbereichs-Zusätze in Klammern an
# (z.B. "C 3.24 Hörsaal (Sozialwesen)"). Mehrfach-Klammern und URLs
# sind möglich ("D 014 Hörsaal (Bank) (auch als PC-Raum nutzbar)",
# "C 1.23 Cubes 1-4 (bitte auch buchen über: https://...)"). Der
# Fachbereich ist redundant — wir entfernen alle Klammer-Gruppen und
# kollabieren Whitespace. [^)]* verzichtet bewusst auf verschachtelte
# Klammern — in Rapla kommen ausschließlich flache Gruppen vor.
_PAREN_RE = re.compile(r"\s*\([^)]*\)")


def _clean_room_name(text):
    """Entferne alle Klammer-Zusätze aus einem Rapla-Raumnamen."""
    cleaned = _PAREN_RE.sub("", text)
    return " ".join(cleaned.split())


def extract_rooms_from_block(cell):
    """Extrahiere Raumnamen aus einer Rapla week_block-Zelle.

    Strategie: Durchsuche alle <span class="resource"> Elemente und filtere
    mit der Raumnamen-Heuristik (Präfix-Regex). Kursgruppen und Dozenten
    werden dadurch ausgeblendet. Vor der Heuristik werden Klammer-Zusätze
    (`(Sozialwesen)`, URLs, etc.) entfernt — der kanonische Schlüssel ist
    der gesäuberte Name.

    Rückgabe: Liste der vollständigen Raumnamen (kann mehrere enthalten bei
    Splitkursen, leer wenn kein Raum gefunden wurde).
    """
    rooms = []
    seen = set()
    for span in cell.find_all("span", class_="resource"):
        txt = _clean_room_name(span.get_text().strip())
        if _is_room_name(txt) and txt not in seen:
            rooms.append(txt)
            seen.add(txt)
    return rooms


def parse_rapla_week_rooms(day, month, year):
    """Hole und parse eine Rapla-Woche mit Raumextraktion.

    Rückgabe:
        {
          "week": "KW 15",
          "days": [
            {
              "label": "Mo 06.04.",
              "date": "2026-04-06",
              "is_holiday": False,
              "events": [
                {"start": "08:00", "end": "09:30", "rooms": ["A1.01"]},
                ...
              ]
            }, ...
          ]
        }
        oder None bei Parse-Fehler.
    """
    url = f"{RAPLA_BASE}&day={day}&month={month}&year={year}"
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    table = soup.find("table", class_="week_table")
    if not table:
        return None

    week_num = ""
    wn = table.find("th", class_="week_number")
    if wn:
        week_num = wn.get_text().strip()

    rows = table.find_all("tr")

    # Tagesspaltengrenzen aus Header parsen
    day_boundaries = []  # [(label, start_col, end_col)]
    col = 0
    for cell in rows[0].find_all(["th", "td"]):
        cs = int(cell.get("colspan", 1))
        if "week_header" in cell.get("class", []):
            nobr = cell.find("nobr")
            label = nobr.get_text().strip() if nobr else cell.get_text().strip()
            day_boundaries.append((label, col, col + cs - 1))
        col += cs

    def day_for_col(c):
        for lbl, s, e in day_boundaries:
            if s <= c <= e:
                return lbl
        return None

    events_by_day = {lbl: [] for lbl, _, _ in day_boundaries}
    # Für Debug/Kalibrierung: Zellen, in denen kein Raum gefunden wurde
    unknown_cells = []

    rowspan_cells = {}
    for row in rows[1:]:
        for c in list(rowspan_cells):
            rowspan_cells[c] -= 1
            if rowspan_cells[c] <= 0:
                del rowspan_cells[c]

        col = 0
        for cell in row.find_all(["td", "th"]):
            while col in rowspan_cells:
                col += 1

            cs = int(cell.get("colspan", 1))
            rs = int(cell.get("rowspan", 1))

            if "week_block" in cell.get("class", []):
                text = cell.get_text()
                m = TIME_RE.search(text)
                if m:
                    text_lower = text.lower()
                    is_online = "online" in text_lower
                    is_excursion = "ausflug" in text_lower or "exkursion" in text_lower
                    if not is_online and not is_excursion:
                        lbl = day_for_col(col)
                        if lbl:
                            rooms = extract_rooms_from_block(cell)
                            if not rooms:
                                sample = " ".join(text.split())[:200]
                                if len(unknown_cells) < 5 and sample not in unknown_cells:
                                    unknown_cells.append(sample)
                            events_by_day[lbl].append({
                                "start": m.group(1),
                                "end": m.group(2),
                                "rooms": rooms,
                            })

            if rs > 1:
                for c in range(col, col + cs):
                    rowspan_cells[c] = rs

            col += cs

    holidays = _holidays_bw(year)
    results = []
    for label, _, _ in day_boundaries:
        events = events_by_day.get(label, [])
        parts = label.split()[-1].rstrip(".").split(".")
        current_date = date(year, int(parts[1]), int(parts[0]))
        is_holiday = current_date in holidays
        results.append({
            "label": label,
            "date": current_date.isoformat(),
            "is_holiday": is_holiday,
            "events": events,
        })

    return {"week": week_num, "days": results, "_unknown_cells": unknown_cells}


def compute_free_slots(
    busy_intervals,
    open_start=8 * 60,
    open_end=20 * 60,
    min_free_minutes=15,
):
    """Berechne freie Zeitfenster zwischen belegten Intervallen.

    Args:
        busy_intervals: Liste von (start_min, end_min) in Minuten seit Mitternacht.
        open_start: Beginn des Betrachtungsfensters in Minuten (Default 08:00).
        open_end: Ende des Betrachtungsfensters (Default 20:00).
        min_free_minutes: Kürzere freie Slots werden verworfen (Default 15).

    Rückgabe: Liste von (start_min, end_min) der freien Slots.
    """
    # 1. Clip auf Öffnungszeit + verwerfe leere/ungültige Intervalle
    clipped = []
    for s, e in busy_intervals:
        if e <= s:
            continue  # ungültig (z.B. über Mitternacht)
        cs = max(s, open_start)
        ce = min(e, open_end)
        if cs < ce:
            clipped.append((cs, ce))

    # 2. Sort + Merge überlappender Intervalle
    clipped.sort()
    merged = []
    for s, e in clipped:
        if merged and s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))

    # 3. Invertiere zu freien Slots
    free = []
    cursor = open_start
    for s, e in merged:
        if s > cursor:
            free.append((cursor, s))
        cursor = e
    if cursor < open_end:
        free.append((cursor, open_end))

    # 4. Filter zu kurze Slots
    return [(s, e) for s, e in free if (e - s) >= min_free_minutes]


def build_day_free_rooms(events, rooms_list, day_date, is_holiday,
                          open_start=8 * 60, open_end=20 * 60,
                          min_free_minutes=15):
    """Berechne für jeden Raum die freien Slots an einem Tag.

    Args:
        events: Liste der Events des Tages (aus parse_rapla_week_rooms).
        rooms_list: Liste der zu betrachtenden Raumnamen.
        day_date: datetime.date des Tages.
        is_holiday: Feiertags-Flag.

    Rückgabe:
        {
          "A1.01": {"status": "partial", "free": [[480, 540], [780, 1200]]},
          "A1.02": {"status": "free_all_day"},
          ...
        }

    status-Werte:
        "free_all_day" — komplett frei (Wochenende, Feiertag oder keine Events)
        "holiday"      — Feiertag
        "partial"      — teilweise frei (free enthält die Slots)
        "busy_all_day" — ganz belegt (free leer)
    """
    is_weekend = day_date.weekday() >= 5  # Sa=5, So=6
    result = {}

    for room in rooms_list:
        if is_holiday:
            result[room] = {"status": "holiday", "free": []}
            continue
        if is_weekend:
            result[room] = {"status": "free_all_day", "free": []}
            continue

        busy = []
        for ev in events:
            if room in ev.get("rooms", []):
                busy.append((
                    time_to_minutes(ev["start"]),
                    time_to_minutes(ev["end"]),
                ))

        if not busy:
            result[room] = {"status": "free_all_day", "free": []}
            continue

        free = compute_free_slots(busy, open_start, open_end, min_free_minutes)
        if not free:
            result[room] = {"status": "busy_all_day", "free": []}
        else:
            # Wenn der einzige freie Slot exakt das gesamte Fenster ist, "free_all_day"
            if len(free) == 1 and free[0] == (open_start, open_end):
                result[room] = {"status": "free_all_day", "free": []}
            else:
                result[room] = {
                    "status": "partial",
                    "free": [list(slot) for slot in free],
                }

    return result
