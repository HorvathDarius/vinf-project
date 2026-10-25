import os 
from extract import extract_driver ,extract_race_result, extract_race_report, extract_team, extract_track

PAGES = os.path.join(os.path.dirname(__file__), "pages")

# Read a saved test page
def read_page(filename):
    with open(os.path.join(PAGES, filename), "r", encoding="utf-8") as f:
        return f.read()

# DRIVERS

# Dead driver, place of birth with diacritics
def test_driver_dead_with_titles():
    driver = extract_driver(read_page("ayrton-senna.html"), "ayrton-senna")
    assert driver["id"] == "driver:ayrton-senna"
    assert driver["name"] == "Ayrton Senna"
    assert driver["birth_date"] == "1960-03-21"
    assert driver["death_date"] == "1994-05-01"
    assert driver["nationality"] == "Brazilian"
    assert driver["f1_titles"] == [1988, 1990, 1991]
    assert driver["place_of_birth"] == "São Paulo"
    assert driver["f1_stats"] == {"races": 149, "wins": 39, "podiums": 75, "poles": 64}

# Living driver has no death date
def test_driver_alive():
    driver = extract_driver(read_page("lewis-hamilton.html"), "lewis-hamilton")
    assert driver["death_date"] is None
    assert driver["f1_titles"] == [2008, 2014, 2015, 2017, 2018, 2019, 2020]
    assert driver["place_of_birth"] == "Tewin, Stevenage, Hertfordshire"
    assert driver["f1_stats"]["races"] == 424
    assert driver["f1_stats"]["wins"] == 105

# Place of birth with a comma and diacritics
def test_driver_place_of_birth():
    driver = extract_driver(read_page("michael-schumacher.html"), "michael-schumacher")
    assert driver["nationality"] == "German"
    assert driver["place_of_birth"] == "Hürth, Nordrhein-Westfalen"
    assert driver["f1_titles"] == [1994, 1995, 2000, 2001, 2002, 2003, 2004]

# 1950s titles use an older award name
def test_driver_1950s_titles():
    driver = extract_driver(read_page("juan-manuel-fangio.html"), "juan-manuel-fangio")
    assert driver["birth_date"] == "1911-06-24"
    assert driver["death_date"] == "1995-07-17"
    assert driver["f1_titles"] == [1951, 1954, 1955, 1956, 1957]
    assert driver["f1_stats"]["wins"] == 24

# Driver without a championship title
def test_driver_without_titles():
    driver = extract_driver(read_page("oscar-piastri.html"), "oscar-piastri")
    assert driver["f1_titles"] == []
    assert driver["place_of_birth"] == "Melbourne"
    assert driver["f1_stats"]["races"] == 105
    assert driver["f1_stats"]["wins"] == 12


# RACE RESULTS

# Modern race, fields of the winner's record
def test_race_result_fields():
    race = extract_race_result(read_page("2021-22.html"), "2021-round-22")
    assert race["id"] == "race:2021-round-22"
    assert race["year"] == 2021
    assert race["round"] == 22
    assert race["name"] == "Formula 1 Saudi Arabian Grand Prix"
    assert race["date"] == "2021-12-05"
    assert race["track"] == "Jeddah Corniche Circuit"
    assert race["winner"] == "Max Verstappen"
    assert len(race["results"]) == 20
    winner = race["results"][0]
    assert winner["team"] == "Red Bull"
    assert winner["car_number"] == "33"
    assert winner["grid"] == 1
    assert winner["laps"] == 58
    assert winner["points"] == 26.0

# Two drivers shared the winning car
def test_race_shared_drive():
    race = extract_race_result(read_page("1957-5.html"), "1957-round-5")
    assert race["winner"] == "Tony Brooks / Stirling Moss"

# driverdb has no team for 1991-2014 results
def test_race_missing_team():
    race = extract_race_result(read_page("1994-3.html"), "1994-round-3")
    assert race["winner"] == "Michael Schumacher"
    assert race["results"][0]["team"] is None

# Name with an HTML entity (apostrophe)
def test_race_name_with_entity():
    race = extract_race_result(read_page("1950-1.html"), "1950-round-1")
    assert race["name"] == "The Royal Automobile Club Grand Prix d'Europe incorporating the British Grand Prix"
    assert race["winner"] == "Giuseppe Farina"
    assert len(race["results"]) == 23


# RACE REPORTS

# Info block, non-breaking space in the event name
def test_report_info_block():
    key = "race-results-2021-abu-dhabi-f1-grand-prix"
    report = extract_race_report(read_page(f"2021-{key}.html"), key)
    assert report["title"] == "Race Results 2021 Abu Dhabi F1 Grand Prix"
    assert report["date"] == "2021-12-12"
    assert report["year"] == 2021
    assert report["event"] == "Abu Dhabi Grand Prix"
    assert report["track"] == "Yas Marina Circuit"
    assert report["weather"] == "dry 28.6°C"
    assert report["winner"] == "Max Verstappen"
    assert report["results"][0]["time"] == "1:30:17.345"

# Results table rows
def test_report_results_table():
    key = "results-1989-formula-1-grand-prix-of-japan"
    report = extract_race_report(read_page(f"1989-{key}.html"), key)
    assert report["winner"] == "Alessandro Nannini"
    assert len(report["results"]) == 26
    first = report["results"][0]
    assert first["team"] == "Benetton"
    assert first["grid"] == 6
    assert first["points"] == 9.0

# Article text is extracted
def test_report_article():
    key = "results-1994-formula-1-grand-prix-of-san-marino"
    report = extract_race_report(read_page(f"1994-{key}.html"), key)
    assert report["track"] == "Autodromo Imola"
    assert report["weather"] == "sunny, dry, warm"
    assert report["results"][0]["team"] == "Benetton"
    assert "Senna" in report["article"]

# Page without a results table
def test_report_without_results_table():
    key = "results-1999-formula-1-grand-prix-of-san-marino"
    report = extract_race_report(read_page(f"1999-{key}.html"), key)
    assert report["results"] == []
    assert report["winner"] is None


# TEAMS

# Team with headquarters and principal
def test_team_all_fields():
    team = extract_team(read_page("mclaren.html"), "mclaren")
    assert team["name"] == "McLaren"
    assert team["full_name"] == "McLaren Mastercard F1 Team"
    assert team["country"] == "Great Britain"
    assert team["headquarters"] == "Woking"
    assert team["principal"] == "Andrea Stella"
    assert team["description"].startswith("McLaren entered Formula 1 in 1966")

# Missing headquarters and principal are None
def test_team_missing_fields():
    team = extract_team(read_page("ferrari.html"), "ferrari")
    assert team["full_name"] == "Scuderia Ferrari HP"
    assert team["country"] == "Italy"
    assert team["headquarters"] is None
    assert team["principal"] is None
    assert "Enzo Ferrari" in team["description"]

# Full name differs from the short name
def test_team_full_name():
    team = extract_team(read_page("williams.html"), "williams")
    assert team["name"] == "Williams"
    assert team["full_name"] == "Atlassian Williams F1 Team"

# No JSON-LD, name comes from <title>
def test_team_title_fallback():
    team = extract_team(read_page("Écurie-rosier.html"), "Écurie-rosier")
    assert team["name"] == "Écurie Rosier"
    assert team["description"] is None


# TRACKS

# Name, country, coordinates and layouts
def test_track_fields():
    track = extract_track(read_page("suzuka.html"), "suzuka")
    assert track["name"] == "Suzuka International Racing Course"
    assert track["country"] == "JP"
    assert track["latitude"] == 34.8431
    assert track["longitude"] == 136.541
    assert len(track["layouts"]) == 4
    assert track["layouts"][0] == {"name": "Grand Prix Circuit 2003", "length_meters": 5807, "active_from": 2003, "active_to": None}

# Track description
def test_track_description():
    track = extract_track(read_page("monza.html"), "monza")
    assert track["description"].startswith("Monza, officially known as the Autodromo Nazionale Monza")
    assert len(track["layouts"]) == 11

# Source has a wrong sign of the longitude (real value is about -1.02)
def test_track_coordinates_as_in_source():
    track = extract_track(read_page("silverstone.html"), "silverstone")
    assert track["latitude"] == 52.0922
    assert track["longitude"] == 1.026

# Track without coordinates and description
def test_track_missing_fields():
    track = extract_track(read_page("aintree.html"), "aintree")
    assert track["latitude"] is None
    assert track["longitude"] is None
    assert track["description"] is None
    assert track["layouts"] == [{"name": "Grand Prix Circuit", "length_meters": 4828, "active_from": 1954, "active_to": 1964}]

# Layouts with historic years
def test_track_layouts():
    track = extract_track(read_page("monte-carlo.html"), "monte-carlo")
    assert track["name"] == "Circuit de Monaco"
    assert track["country"] == "MC"
    assert len(track["layouts"]) == 9
    assert track["layouts"][-1]["active_from"] == 1929