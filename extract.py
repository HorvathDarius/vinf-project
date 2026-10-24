import re
import json
import os
import html as html_lib
from crawl import DRIVER_LOG_PATH, RACE_RESULTS_LOG_PATH, TEAMS_LOG_PATH, TRACKS_LOG_PATH
from crawl_fansite import RACE_REPORTS_LOG_PATH

EXTRACTED_DIR = "extracted"
DRIVERS_JSONL = EXTRACTED_DIR + "/drivers.jsonl"
RACE_RESULTS_JSONL = EXTRACTED_DIR + "/race_results.jsonl"
RACE_REPORTS_JSONL = EXTRACTED_DIR + "/race_reports.jsonl"
TEAMS_JSONL = EXTRACTED_DIR + "/teams.jsonl"
TRACKS_JSONL = EXTRACTED_DIR + "/tracks.jsonl"


# DRIVERS
# JSON-LD block with the page's main person (plain JSON, not escaped)
PERSON_RE = re.compile(r'"@type":"Person",(.*?)</script>')
NAME_RE = re.compile(r'"name":"([^"]+)"')
BIRTH_DATE_RE = re.compile(r'"birthDate":"([^"]+)"')
DEATH_DATE_RE = re.compile(r'"deathDate":"([^"]+)"')
NATIONALITY_RE = re.compile(r'"nationality":\{"@type":"Country","name":"([^"]+)"')
AWARDS_RE = re.compile(r'"award":\[(.*?)\]')
AWARD_ITEM_RE = re.compile(r'"([^"]+)"')
F1_TITLE_RE = re.compile(
    r'^(\d{4}) (FIA World Championship of Drivers|FIA World Championship Formula One'
    r'|FIA Formula One World Championship|FIA Formula 1 World Championship)$'
)
# Escaped NEXT.JS JSON - the page has records of several drivers, so we create a link back to the driver
PLACES_RE = (
    r'\\"place_of_birth\\":(?:\\"([^"]*?)\\"|null),\\"dod\\":[^,]*,'
    r'\\"place_of_death\\":(?:\\"([^"]*?)\\"|null),\\"ddb_url\\":\\"{slug}\\"'
)
# F1 stats block (the page also has stats from other series)
F1_STATS_RE = re.compile(
    r'\\"legacy_url\\":\\"formula-1\\",\\"championship_id\\":1,\\"stats\\":'
    r'{\\"races\\":(\d+),\\"wins\\":(\d+),\\"podiums\\":(\d+),\\"poles\\":(\d+)'
)
# Escaped whitespaces from inside JSON strings
ESCAPED_WS_RE = re.compile(r'\\+[tnr]')



# RACE-RESUTLS
# Race page: name, date and track
RACE_NAME_RE = re.compile(r'<h1[^>]*>([^<]+)</h1>')
RACE_DATE_RE = re.compile(r'"@type":"SportsEvent".*?"startDate":"([^"]+)"')
RACE_TRACK_RE = re.compile(r'"@type":"SportsActivityLocation","name":"([^"]+)"')
# Result records in escaped JSON
RESULT_START_RE = re.compile(r'\{\\"session_results_id\\":(\d+),')
POSITION_RE = re.compile(r'\\"finish_position\\":(\d+)')
GRID_RE = re.compile(r'\\"grid_position\\":(\d+)')
STATUS_RE = re.compile(r'\\"finish_status\\":\\"([^"\\]+)\\"')
LAPS_RE = re.compile(r'\\"total_driving_laps\\":(\d+)')
POINTS_RE = re.compile(r'\\"championship_points\\":([\d.]+)')
CAR_NUMBER_RE = re.compile(r'\\"car_number\\":\\"([^"\\]+)\\"')
RESULT_DRIVER_NAME_RE = re.compile(r'\\"full_name\\":\\"([^"\\]+)\\"')
RESULT_DRIVER_SLUG_RE = re.compile(r'\\"profile_url\\":\\"/drivers/([^"\\]+)\\"')
RESULT_TEAM_RE = re.compile(r'\\"team\\":\{\\"id\\":\d+,\\"name\\":\\"([^"\\]+)\\"')



# RACE REPORTS
# f1-fansite race report: Wordpress HTML
REPORT_TITLE_RE = re.compile(r'<h1[^>]*>\s*([^<]+?)\s*</h1>')
REPORT_DATE_RE = re.compile(r'<time class="entry-date"[^>]*datetime="(\d{4}-\d{2}-\d{2})')
REPORT_EVENT_RE = re.compile(r'Event:(?:</strong>)?\s*<a[^>]*>([^<]+)</a>')
REPORT_TRACK_RE = re.compile(r'Track:(?:</strong>)?\s*<a[^>]*>([^<]+)</a>')
REPORT_WEATHER_RE = re.compile(r'Weather:(?:</strong>)?\s*(.*?)(?:<br|</p>)', re.DOTALL)
REPORT_YEAR_RE = re.compile(r'(?:19|20)\d{2}')
# Article
REPORT_ARTICLE_RE = re.compile(
    r'<div id="post-\d+" class="entry [^"]*"\s*>(.*?)'
    r'(?:<h[23][^>]*>[^<]*</h[23]>\s*)?<div id="msr_result"',
    re.DOTALL,
)
# Results table and its rows
REPORT_TABLE_RE = re.compile(r'<table class="motor-sport-results msr_result[^"]*">(.*?)</table>', re.DOTALL)
REPORT_ROW_RE = re.compile(r'<tr[^>]*>(.*?)</tr>', re.DOTALL)
ROW_POSITION_RE = re.compile(r'msr-rank-badge">(\d+)<')
ROW_NUMBER_RE = re.compile(r'<th class="msr_col2">([^<]*)<')
ROW_DRIVER_RE = re.compile(r'class="msr-driver-name[^"]*"[^>]*aria-label="([^"]+)"')
# Team cell has two markups (with and without msr-result-team span), anchor on the col
ROW_TEAM_RE = re.compile(r'<td class="msr_col4">.*?<a [^>]*>([^<]+)</a>', re.DOTALL)
ROW_GRID_RE = re.compile(r'<td class="msr_col8">(\d+)<')
ROW_LAPS_RE = re.compile(r'<td class="msr_col6">(\d+)<')
ROW_STATUS_RE = re.compile(r'msr-rank-classified"[^>]*>([^<]+)<')
# Finish time, or retirement reason
ROW_TIME_RE = re.compile(r'<td class="msr_col5">([^<]+)<')
ROW_POINTS_RE = re.compile(r'<td class="msr_col9">([\d.]+)<')
# Remove tags, decode entities, collapse whitespace
TAGS_RE = re.compile(r'<[^>]+>')
SCRIPT_STYLE_RE = re.compile(r'<(script|style|nav)[^>]*>.*?</\1>', re.DOTALL)
WHITESPACE_RE = re.compile(r'\s+')



# TEAMS
TEAM_LD_RE = re.compile(r'"@type":"SportsTeam","name":"([^"]+)","url":"[^"]*"(?:,"description":"((?:[^"\\]|\\.)*)")?')
TEAM_TITLE_RE = re.compile(r'<title>([^<]+?) – ')
TEAM_FULL_NAME_RE = r'\\"name\\":\\"([^"\\]+)\\",\\"team_ddb_url\\":\\"{slug}\\"'
TEAM_COUNTRY_RE = r'\\"team_ddb_url\\":\\"{slug}\\",\\"country\\":\{{\\"id\\":\d+,\\"name\\":\\"([^"\\]+)\\"'
HEADQUARTERS_RE = re.compile(r'\\"headquarters\\":\\"([^"\\]+)\\"')
PRINCIPAL_RE = re.compile(r'\\"principal\\":\\"([^"\\]+)\\"')



# TRACKS
TRACK_NAME_RE = re.compile(r'"@type":"SportsActivityLocation","name":"([^"]+)"')
TRACK_COUNTRY_RE = re.compile(r'"addressCountry":"([^"]+)"')
TRACK_GEO_RE = re.compile(r'"latitude":(-?[\d.]+),"longitude":(-?[\d.]+)')
TRACK_DESCRIPTION_RE = re.compile(r'>Track Information</h3><p[^>]*>(.*?)</p>', re.DOTALL)
NO_DESCRIPTION = "No information available."
LAYOUTS_RE = re.compile(r'\\"layouts\\":\[(.*?)\]')
LAYOUT_ITEM_RE = re.compile(
    r'\\"layout_name\\":(?:\\"([^"\\]*)\\"|null),\\"length_meters\\":(\d+|null),'
    r'\\"active_from\\":(\d+|null),\\"active_to\\":(\d+|null)'
)



# HELPER FUNCTIONS

# Clean a value from escaped JSON, empty string -> None
def clean_value(value):
    if value is None:
        return None
    value = ESCAPED_WS_RE.sub(" ", value).strip()
    return value or None

# Decode HTML entitites
def clean_html_text(text):
    if text is None:
        return None
    return html_lib.unescape(text).strip()

# Strip tags, scripts and nav, decode HTML entities, collapse whitespace
def html_to_text(fragment):
    fragment = SCRIPT_STYLE_RE.sub(" ", fragment)
    text = html_lib.unescape(TAGS_RE.sub(" ", fragment))
    return WHITESPACE_RE.sub(" ", text).strip()

# Return the first group of the first match or None
def first_match(pattern, text):
    match = pattern.search(text)
    if match:
        return match.group(1)
    return None

# Return the first number group as int/float or None
def first_number(pattern, text, number_type=int):
    value = first_match(pattern, text)
    if value is None:
        return None
    return number_type(value)

# Convert a number captured from JSON to int
def int_or_none(value):
    if value == "null":
        return None
    return int(value)

# Driver with position 1, None if the race has no classified winner
def find_winner(results):
    winners = [result["driver"] for result in results if result["position"] == 1]
    return " / ".join(winners) or None

# Read crawl log and return (key, path, url) of pages saved with status 200
def read_crawled(log_path):
    pages = []
    with open(log_path, encoding="utf-8") as f:
        next(f)  # Skip header
        for line in f:
            status, key, path, url = line.rstrip("\n").split("\t")
            if status == "200" and os.path.exists(path):
                pages.append((key, path, url))
    return pages

# Extract the year from a report key or date
def report_year(key, date):
    match = REPORT_YEAR_RE.search(key)
    if match:
        return int(match.group(0))
    return int(date[:4])


# DRIVERS

# Extract driver fields from the driver HTML page
def extract_driver(html, slug):
    person = first_match(PERSON_RE, html) or ""

    awards = []
    awards_block = first_match(AWARDS_RE, person)
    if awards_block:
        awards = AWARD_ITEM_RE.findall(awards_block)

    f1_titles = []
    for award in awards:
        match = F1_TITLE_RE.match(award)
        if match:
            f1_titles.append(int(match.group(1)))

    place_of_birth = None
    place_of_death = None
    places = re.search(PLACES_RE.format(slug=re.escape(slug)), html)
    if places:
        place_of_birth = clean_value(places.group(1))
        place_of_death = clean_value(places.group(2))

    f1_stats = {}
    stats = F1_STATS_RE.search(html)
    if stats:
        f1_stats = {
            "races": int(stats.group(1)),
            "wins": int(stats.group(2)),
            "podiums": int(stats.group(3)),
            "poles": int(stats.group(4)),
        }

    return {
        "id": f"driver:{slug}",
        "type": "driver",
        "name": first_match(NAME_RE, person),
        "birth_date": first_match(BIRTH_DATE_RE, person),
        "death_date": first_match(DEATH_DATE_RE, person),
        "nationality": first_match(NATIONALITY_RE, person),
        "f1_titles": sorted(f1_titles),
        "awards": awards,
        "place_of_birth": place_of_birth,
        "place_of_death": place_of_death,
        "f1_stats": f1_stats,
    }

# Build searchable txt from the extracted driver fields
def driver_text(driver):
    parts = [
        driver["name"],
        driver["nationality"],
        driver["place_of_birth"],
        driver["place_of_death"],
    ]
    for year in driver["f1_titles"]:
        parts.append(f"{year} Formula 1 World Champion")
    parts.extend(driver["awards"])
    # Skip fields that are None
    return " ".join(part for part in parts if part)



# RACE RESUTLS

# Split the page into result records and extract fields
def extract_results(html):
    starts = list(RESULT_START_RE.finditer(html))
    results = {}
    for i, start in enumerate(starts):
        result_id = start.group(1)
        # Each records is on the page twice, keep the first one
        if result_id in results:
            continue
        # Record segment: from this record to the start of the next one
        if i+1 < len(starts):
            end = starts[i+1].start()
        else:
            end = len(html)
        segment = html[start.start():end]
        results[result_id] = {
            "position": first_number(POSITION_RE, segment),
            "driver": first_match(RESULT_DRIVER_NAME_RE, segment),
            "driver_slug": first_match(RESULT_DRIVER_SLUG_RE, segment),
            "team": first_match(RESULT_TEAM_RE, segment),
            "car_number": first_match(CAR_NUMBER_RE, segment),
            "grid": first_number(GRID_RE, segment),
            "laps": first_number(LAPS_RE, segment),
            "points": first_number(POINTS_RE, segment, float),
            "status": first_match(STATUS_RE, segment) or "finished",
        }
    return list(results.values())

# Extract race fields from the race result page
def extract_race_result(html, key):
    year, round_number = key.split("-round-")
    results = extract_results(html)

    winner = find_winner(results)

    return {
        "id": f"race:{key}",
        "type": "race_result",
        "year": int(year),
        "round": int(round_number),
        "name": clean_html_text(first_match(RACE_NAME_RE, html)),
        "date": first_match(RACE_DATE_RE, html),
        "track": first_match(RACE_TRACK_RE, html),
        "winner": winner,
        "results": results,
    } 

# Build searchable text from the extracted race fields
def race_result_text(race):
    parts = [race["name"], str(race["year"]), race["track"]]
    if race["winner"]:
        parts.append(f"winner {race["winner"]}")
    for result in race["results"]:
        parts.append(result["driver"])
        parts.append(result["team"])
        parts.append(result["status"])
    return " ".join(part for part in parts if part)



# RACE REPORTS

# Extract result rows from the f1-fansite results table
def extract_report_results(html):
    table = first_match(REPORT_TABLE_RE, html)
    if table is None:
        return []
    results = []
    for row in REPORT_ROW_RE.findall(table):
        # Skip header 
        driver = first_match(ROW_DRIVER_RE, row)
        if driver is None:
            continue
        results.append({
            "position": first_number(ROW_POSITION_RE, row),
            "car_number": first_match(ROW_NUMBER_RE, row),
            "driver": clean_html_text(driver),
            "team": clean_html_text(first_match(ROW_TEAM_RE, row)),
            "grid": first_number(ROW_GRID_RE, row),
            "laps": first_number(ROW_LAPS_RE, row),
            "time": clean_html_text(first_match(ROW_TIME_RE, row)),
            "points": first_number(ROW_POINTS_RE, row, float),
            "status": first_match(ROW_STATUS_RE, row) or "finished"
        })
    return results

# Extract race report fields from the f1-fansite HTML page
def extract_race_report(html, key):
    results = extract_report_results(html)
    winner = find_winner(results)

    date = first_match(REPORT_DATE_RE, html)

    article = first_match(REPORT_ARTICLE_RE, html) or ""
    return {
        "id": f"report:{key}",
        "type": "race_report",
        "title": clean_html_text(first_match(REPORT_TITLE_RE, html)),
        "date": date,
        "year": report_year(key, date),
        "event": clean_html_text(first_match(REPORT_EVENT_RE, html)),
        "track": clean_html_text(first_match(REPORT_TRACK_RE, html)),
        "weather": html_to_text(first_match(REPORT_WEATHER_RE, html) or "") or None,
        "winner": winner,
        "results": results,
        "article": html_to_text(article),
    }

# Build searchable text from the extracted race report fields
def race_report_text(report):
    parts = [report["title"], report["article"]]
    for result in report["results"]:
        parts.append(result["driver"])
        parts.append(result["team"])
        # For driver who did not finish, time holds the reason
        if result["status"] != "finished":
            parts.append(result["status"])
            parts.append(result["time"])
    return " ".join(part for part in parts if part)



# TEAMS

# Extract team fields from the team HTML page
def extract_team(html, slug):
    name = None
    description = None
    team_ld = TEAM_LD_RE.search(html)
    if team_ld:
        name = team_ld.group(1)
        description = clean_value(team_ld.group(2))
    else:
        name = first_match(TEAM_TITLE_RE, html)

    slug_re = re.escape(slug)
    return {
        "id": f"team:{slug}",
        "type": "team",
        "name": clean_html_text(name) if name else None,
        "full_name": first_match(re.compile(TEAM_FULL_NAME_RE.format(slug=slug_re)), html),
        "country": first_match(re.compile(TEAM_COUNTRY_RE.format(slug=slug_re)), html),
        "headquarters": first_match(HEADQUARTERS_RE, html),
        "principal": first_match(PRINCIPAL_RE, html),
        "description": clean_html_text(description) if description else None,
    }

# Build the text for the index from the team fields
def team_text(team):
    parts = [team["name"], team["full_name"], team["country"], team["headquarters"], team["principal"], team["description"]]
    return " ".join(part for part in parts if part)



# TRACKS

# Extract the list of track layouts
def extract_layouts(html):
    layouts = []
    block = first_match(LAYOUTS_RE, html)
    if not block:
        return layouts
    for name, length, active_from, active_to in LAYOUT_ITEM_RE.findall(block):
        layouts.append({
            "name": clean_html_text(name) or None,
            "length_meters": int_or_none(length),
            "active_from": int_or_none(active_from),
            "active_to": int_or_none(active_to),
        })
    return layouts

# Extract track fields from the track HTML page
def extract_track(html, slug):
    latitude = None
    longitude = None
    geo = TRACK_GEO_RE.search(html)
    if geo:
        latitude = float(geo.group(1))
        longitude = float(geo.group(2))

    description = first_match(TRACK_DESCRIPTION_RE, html)
    if description:
        description = html_to_text(description)
    if description == NO_DESCRIPTION:
        description = None

    name = first_match(TRACK_NAME_RE, html)
    return {
        "id": f"track:{slug}",
        "type": "track",
        "name": clean_html_text(name) if name else None,
        "country": first_match(TRACK_COUNTRY_RE, html),
        "latitude": latitude,
        "longitude": longitude,
        "description": description,
        "layouts": extract_layouts(html),
    }

# Build the text for the index from the track fields
def track_text(track):
    parts = [track["name"], track["country"], track["description"]]
    for layout in track["layouts"]:
        parts.append(layout["name"])
    return " ".join(part for part in parts if part)



# COMMON EXTRACT

# Extract all crawled pages of on type into a JSONL file
def extract_pages(label, log_path, jsonl_path, extract_page, page_text):
    print(f"===Extracting {label}...===")
    os.makedirs(EXTRACTED_DIR, exist_ok=True)
    pages = read_crawled(log_path)
    with open(jsonl_path, "w", encoding="utf-8") as out:
        for key, path, url in pages:
            with open(path, "r", encoding="utf-8") as f:
                html = f.read()
            page = extract_page(html, key)
            page["source_url"] = url
            page["text"] = page_text(page)
            out.write(json.dumps(page, ensure_ascii=False) + "\n")
    print(f"===Extracted {len(pages)} {label} to {jsonl_path}.===")

# Count how many records have a non-empty value for each field.
# For lists of dicts (e.g. results) also count each nested field over all items.
def coverage(jsonl_path):
    counts = {}
    nested_counts = {}  # "results.team" -> filled items
    nested_totals = {}  # "results" -> number of items
    total = 0
    with open(jsonl_path, encoding="utf-8") as f:
        for line in f:
            record = json.loads(line)
            total += 1
            for field, value in record.items():
                if field not in counts:
                    counts[field] = 0
                # None, "", [] and {} count as missing
                if value:
                    counts[field] += 1

                # Nested: list of dicts
                if isinstance(value, list) and value and isinstance(value[0], dict):
                    nested_totals[field] = nested_totals.get(field, 0) + len(value)
                    for item in value:
                        for sub_field, sub_value in item.items():
                            name = f"{field}.{sub_field}"
                            if name not in nested_counts:
                                nested_counts[name] = 0
                            # 0 is a valid value (e.g. 0 points), only None and "" are missing
                            if sub_value is not None and sub_value != "":
                                nested_counts[name] += 1

    print(f"===Coverage of {jsonl_path} ({total} records)===")
    for field, count in counts.items():
        print(f"\t{field:<20} {count:>6} / {total}  ({count / total * 100:.1f} %)")

    for name, count in nested_counts.items():
        field = name.split(".")[0]
        items = nested_totals[field]
        print(f"\t{name:<20} {count:>6} / {items}  ({count / items * 100:.1f} %)")



EXTRACTORS = [
    ("drivers", DRIVER_LOG_PATH, DRIVERS_JSONL, extract_driver, driver_text),
    ("race_results", RACE_RESULTS_LOG_PATH, RACE_RESULTS_JSONL, extract_race_result, race_result_text),
    ("race_reports", RACE_REPORTS_LOG_PATH, RACE_REPORTS_JSONL, extract_race_report, race_report_text),
    ("teams", TEAMS_LOG_PATH, TEAMS_JSONL, extract_team, team_text),
    ("tracks", TRACKS_LOG_PATH, TRACKS_JSONL, extract_track, track_text),
]

if __name__ == "__main__":
    for label, log_path, jsonl_path, extract_page, page_text in EXTRACTORS:
        extract_pages(label, log_path, jsonl_path, extract_page, page_text)
        coverage(jsonl_path)
