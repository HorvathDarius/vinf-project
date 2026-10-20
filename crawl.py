from common import fetch_and_save, log_page, load_done
import re
import time
import os


BASE_URL = "https://www.driverdb.com"
YEARS = range(1950, 2027)

# DIRS
STANDINGS_DIR = "data/standings"
CALENDAR_DIR = "data/calendars"
TEAMS_BY_YEAR_DIR = "data/teams_year"
TEAMS_DIR = "data/teams"
DRIVER_DIR = "data/drivers"
RACE_RESULTS_DIR = "data/race_results"
TRACKS_DIR = "data/tracks"

# URLS
STANDINGS_URL = BASE_URL + "/championships/formula-1/{year}/standings"
CALENDAR_URL = BASE_URL + "/championships/formula-1/{year}/calendar"
TEAMS_BY_YEAR_URL = BASE_URL + "/championships/formula-1/{year}/teams"
DRIVER_URL = BASE_URL + "/drivers/{driver_slug}"
RACE_RESULTS_URL = BASE_URL + "/championships/formula-1/{year}/results/round-{round_number}/race-1"
TRACKS_URL = BASE_URL + "/tracks/{track_slug}"
TEAMS_URL = BASE_URL + "/teams/{team_slug}"

# LOGS
DRIVER_LOG_PATH = DRIVER_DIR + "/crawl.tsv"
RACE_RESULTS_LOG_PATH = RACE_RESULTS_DIR + "/crawl.tsv"
TRACKS_LOG_PATH = TRACKS_DIR + "/crawl.tsv"
TEAMS_LOG_PATH = TEAMS_DIR + "/crawl.tsv"

# Crawl standings for all years and save them to files
def crawl_standings():
    print("===Crawling standings for all years...===")
    os.makedirs(STANDINGS_DIR, exist_ok=True)
    # For each year in YEARS
    for year in YEARS:
        url = STANDINGS_URL.format(year=year)
        path = os.path.join(STANDINGS_DIR, f"{year}-standings.html")
        # Skip if file already exists
        if os.path.exists(path):
            print(f"\tStandings for {year} already exist. Skipping.")
            continue
        print(f"\tCrawling standings for {year}...")
        response = fetch_and_save(url, path)
        if response is None or response.status_code != 200:
            if response is None:
                status = "No response"
            else:
                status = response.status_code
            print(f"\tFailed to fetch standings for {year}. Status code: {status}")
        time.sleep(2)

# Find all driver slugs in the HTML content of the standings page
def find_driver_slugs(html):
    # set takes care of duplicates
    pattern = r'profile_url\\":\\"/drivers/([^\\]+)'
    slugs = set(re.findall(pattern, html))
    return sorted(slugs)

# Find all driver slugs across all seasons and return a sorted list of unique slugs
def collect_driver_slugs():
    all_slugs = set()
    for year in YEARS:
        path = os.path.join(STANDINGS_DIR, f"{year}-standings.html")
        # Skip seasons whose standings failed to download
        if not os.path.exists(path):
            print(f"===Standings for {year} not found. Skipping.===")
            continue

        with open(path, "r", encoding="utf-8") as f:
            html = f.read()

        slugs = find_driver_slugs(html)
        print(f"===Found {len(slugs)} driver slugs for {year}.===")
        # Set takes care of drivers who raced in multiple seasons
        all_slugs.update(slugs)
    return sorted(all_slugs)

# Crawl all drivers given a list of (index, slug) tuples
def crawl_drivers(slugs):
    print("===Crawling drivers...===")
    # Create dir
    os.makedirs(DRIVER_DIR, exist_ok=True)
    # Load already crawled drivers
    done_drivers = load_done(DRIVER_LOG_PATH)
    for index, slug in slugs:
        # Construct URL
        driver_url = DRIVER_URL.format(driver_slug=slug)
        # If slug in LOG, then skip
        if slug in done_drivers:
            print("\tSkipping driver:", slug, "(", index + 1, "/", len(slugs), ")")
            continue
        # Else crawl
        print ("\tCrawling driver:", slug, "(", index + 1, "/", len(slugs), ")")
        response = fetch_and_save(driver_url, f"{DRIVER_DIR}/{slug}.html")
        if response is None:
            status = "error"
        else:
            status = str(response.status_code)
        log_page(DRIVER_LOG_PATH, status, slug, f"{DRIVER_DIR}/{slug}.html", driver_url)
        time.sleep(2)

    

# Crawl all calendarts for all years and save them to files
def crawl_calendars():
    print("===Crawling calendars for all years...===")
    os.makedirs(CALENDAR_DIR, exist_ok=True)
        # For each year in YEARS
    for year in YEARS:
        url = CALENDAR_URL.format(year=year)
        path = os.path.join(CALENDAR_DIR, f"{year}-calendar.html")
        # Skip if file already exists
        if os.path.exists(path):
            print(f"\tCalendar for {year} already exist. Skipping.")
            continue
        print(f"\tCrawling calendar for {year}...")
        response = fetch_and_save(url, path)
        if response is None or response.status_code != 200:
            if response is None:
                status = "No response"
            else:
                status = response.status_code
            print(f"\tFailed to fetch calendar for {year}. Status code: {status}")
        time.sleep(2)


# Find all round numbers in the HTML content of the calendar page for a given year
def find_round_numbers(html, year):
    pattern = rf'href="/championships/formula-1/{year}/results/round-(\d+)"'
    rounds = set(re.findall(pattern, html))
    round_numbers = []
    for r in rounds:
        round_numbers.append(int(r))
    return sorted(round_numbers)

# Crawl all race results for a given year
def crawl_race_results(race_numbers, year):
    print(f"===Crawling race results for {year}...===")
    # Create dir
    os.makedirs(RACE_RESULTS_DIR, exist_ok=True)
    doe_race_results = load_done(RACE_RESULTS_LOG_PATH)
    for index, number in race_numbers:
        key = f"{year}-round-{number}"
        # Construct URL
        race_url = RACE_RESULTS_URL.format(year=year, round_number=number)
        # If slug in LOG, then skip
        if key in doe_race_results:
            print(f"\tSkipping race: {number} ({index + 1}/{len(race_numbers)})")
            continue
        # Else crawl
        print(f"\tCrawling race result: {number} ({index + 1}/{len(race_numbers)})")
        response = fetch_and_save(race_url, f"{RACE_RESULTS_DIR}/{year}-{number}.html")
        if response is None:
            status = "error"
        else:
            status = str(response.status_code)
        log_page(RACE_RESULTS_LOG_PATH, status, key, f"{RACE_RESULTS_DIR}/{year}-{number}.html", race_url)
        time.sleep(2)

# Crawl all race results for all years
def crawl_all_race_results():
    print("===Crawling race results for all years...===")
    for year in YEARS:
        path = os.path.join(CALENDAR_DIR, f"{year}-calendar.html")
        # Skip seasons whose calendar failed to download
        if not os.path.exists(path):
            print(f"\tCalendar for {year} not found. Skipping.")
            continue

        with open(path, "r", encoding="utf-8") as f:
            html = f.read()

        round_numbers = find_round_numbers(html, year)
        print(f"\tFound {len(round_numbers)} rounds for {year}.")
        round_numbers_with_index = list(enumerate(round_numbers))
        crawl_race_results(round_numbers_with_index, year)



# Find all track slugs in the HTML content of the calendar page
def find_tracks(html):
    pattern = r'href="/tracks/([^"]+)"'
    tracks = set(re.findall(pattern, html))
    track_list = []
    for track in tracks:
        track_list.append(track)
    return sorted(track_list)

# Crawl all tracks given a list of (index, slug) tuples
def crawl_tracks(tracks):
    print(f"===Crawling tracks...===")
    # Create dir
    os.makedirs(TRACKS_DIR, exist_ok=True)
    done_tracks = load_done(TRACKS_LOG_PATH)
    for index, track in tracks:
        key = track
        # Construct URL
        track_url = TRACKS_URL.format(track_slug=track)
        # If slug in LOG, then skip
        if key in done_tracks:
            print(f"\tSkipping track: {track} ({index + 1}/{len(tracks)})")
            continue
        # Else crawl
        print(f"\tCrawling track: {track} ({index + 1}/{len(tracks)})")
        response = fetch_and_save(track_url, f"{TRACKS_DIR}/{track}.html")
        if response is None:
            status = "error"
        else:
            status = str(response.status_code)
        log_page(TRACKS_LOG_PATH, status, key, f"{TRACKS_DIR}/{track}.html", track_url)
        time.sleep(2)

# Find all track slugs across all seasons and return a sorted list of unique slugs
def collect_track_slugs():
    print("===Crawling tracks for all years...===")
    all_tracks = set()
    for year in YEARS:
        path = os.path.join(CALENDAR_DIR, f"{year}-calendar.html")
        # Skip seasons whose tracks failed to download
        if not os.path.exists(path):
            print(f"\tCalendar for {year} not found. Skipping.")
            continue

        with open(path, "r", encoding="utf-8") as f:
            html = f.read()

        tracks = find_tracks(html)
        print(f"\tFound {len(tracks)} tracks for {year}.")
        # Set takes care of tracks used in multiple seasons
        all_tracks.update(tracks)
    return sorted(all_tracks)



# Crawl teams pages from all years and save them to files
def crawl_teams_by_year():
    print("===Crawling teams for all years...===")
    os.makedirs(TEAMS_BY_YEAR_DIR, exist_ok=True)
    # For each year in YEARS
    for year in YEARS:
        url = TEAMS_BY_YEAR_URL.format(year=year)
        path = os.path.join(TEAMS_BY_YEAR_DIR, f"{year}-teams.html")
        # Skip if file already exists
        if os.path.exists(path):
            print(f"\tTeams for {year} already exist. Skipping.")
            continue
        print(f"\tCrawling teams for {year}...")
        response = fetch_and_save(url, path)
        if response is None or response.status_code != 200:
            if response is None:
                status = "No response"
            else:
                status = response.status_code
            print(f"\tFailed to fetch teams for {year}. Status code: {status}")
        time.sleep(2)

# Find all team slugs across all seasons and return a sorted list of unique slugs
def find_team_slugs(html):
    # Find all team slugs in the HTML
    pattern = r'href="/championships/formula-1/\d+/teams/([^"]+)"'
    teams = set(re.findall(pattern, html))
    team_list = []
    for team in teams:
        team_list.append(team)
    return sorted(team_list)

# Find all team slugs across all seasons and return a sorted list of unique slugs
def collect_team_slugs():
    print("===Collecting team slugs for all years...===")
    all_teams = set()
    for year in YEARS:
        path = os.path.join(TEAMS_BY_YEAR_DIR, f"{year}-teams.html")
        # Skip seasons whose teams failed to download
        if not os.path.exists(path):
            print(f"\tTeams for {year} not found. Skipping.")
            continue

        with open(path, "r", encoding="utf-8") as f:
            html = f.read()

        teams = find_team_slugs(html)
        print(f"\tFound {len(teams)} teams for {year}.")
        # Set takes care of teams used in multiple seasons
        all_teams.update(teams)
    return sorted(all_teams)

# Crawl all teams given a list of (index, slug) tuples
def crawl_teams(slugs):
    print(f"===Crawling teams...===")
    # Create dir
    os.makedirs(TEAMS_DIR, exist_ok=True)
    done_teams = load_done(TEAMS_LOG_PATH)
    for index, slug in slugs:
        key = slug
        # Construct URL
        team_url = TEAMS_URL.format(team_slug=slug)
        # If slug in LOG, then skip
        if key in done_teams:
            print(f"\tSkipping team: {slug} ({index + 1}/{len(slugs)})")
            continue
        # Else crawl
        print(f"\tCrawling team: {slug} ({index + 1}/{len(slugs)})")
        response = fetch_and_save(team_url, f"{TEAMS_DIR}/{slug}.html")
        if response is None:
            status = "error"
        else:
            status = str(response.status_code)
        log_page(TEAMS_LOG_PATH, status, key, f"{TEAMS_DIR}/{slug}.html", team_url)
        time.sleep(2)


# Main program
if __name__ == "__main__":
    total_start = time.time()
    start = time.time()

    os.makedirs("data", exist_ok=True)

    # Crawl standings
    crawl_standings()
    # Get all unqiue drivers from standings HTML files
    slugs = collect_driver_slugs()
    print(f"===Found {len(slugs)} unique driver slugs across all seasons.===\n")
    slugs_with_index = list(enumerate(slugs))
    # Crawl all drivers
    crawl_drivers(slugs_with_index)

    # Elapsed time for drivers
    elapsed = time.time() - start
    hours = int(elapsed // 3600)
    minutes = int(elapsed % 3600 // 60)
    seconds = int(elapsed % 60)
    print(f"===DRIVERS - Finished in {hours} h {minutes} min {seconds} s===\n")

    # Crawl calendars
    start = time.time()
    crawl_calendars()

    # Elapsed time for calendar 
    elapsed = time.time() - start
    hours = int(elapsed // 3600)
    minutes = int(elapsed % 3600 // 60)
    seconds = int(elapsed % 60)
    print(f"===CALENDARS - Finished in {hours} h {minutes} min {seconds} s===\n")

    # Crawl race results
    start = time.time()

    crawl_all_race_results()

    # Elapsed time for race results
    elapsed = time.time() - start
    hours = int(elapsed // 3600)
    minutes = int(elapsed % 3600 // 60)
    seconds = int(elapsed % 60)
    print(f"===RACE RESULTS - Finished in {hours} h {minutes} min {seconds} s===\n")

    # Crawl tracks
    start = time.time()

    tracks = collect_track_slugs()
    print(f"===Found {len(tracks)} unique tracks across all seasons.===\n")
    tracks_with_index = list(enumerate(tracks))
    crawl_tracks(tracks_with_index)

    # Elapsed time for race results
    elapsed = time.time() - start
    hours = int(elapsed // 3600)
    minutes = int(elapsed % 3600 // 60)
    seconds = int(elapsed % 60)
    print(f"===TRACKS - Finished in {hours} h {minutes} min {seconds} s===\n")

    # Crawl teams
    start = time.time()

    crawl_teams_by_year()
    team_slugs = collect_team_slugs()
    print(f"===Found {len(team_slugs)} unique team slugs across all seasons.===\n")
    team_slugs_with_index = list(enumerate(team_slugs))
    print(team_slugs)
    crawl_teams(team_slugs_with_index)


    # Elapsed time for teams
    elapsed = time.time() - start
    hours = int(elapsed // 3600)
    minutes = int(elapsed % 3600 // 60)
    seconds = int(elapsed % 60)
    print(f"===TEAMS - Finished in {hours} h {minutes} min {seconds} s===\n")

    # Total elapsed time
    total_elapsed = time.time() - total_start
    total_hours = int(total_elapsed // 3600)
    total_minutes = int(total_elapsed % 3600 // 60)
    total_seconds = int(total_elapsed % 60)
    print(f"\n===TOTAL - Finished in {total_hours} h {total_minutes} min {total_seconds} s===" + "\n")