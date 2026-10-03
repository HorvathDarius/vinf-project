import requests
import re
import os
import time

HEADERS = {"User-Agent": "VINF-F1-crawler/0.1 (FIIT STU student project)"}

BASE_URL = "https://www.driverdb.com"
YEARS = range(2025, 2027)

STANDINGS_URL = BASE_URL + "/championships/formula-1/{year}/standings"
STANDINGS_DIR = "data/standings"

CALENDAR_URL = BASE_URL + "/championships/formula-1/{year}/calendar"
CALENDAR_DIR = "data/calendars"

RETRIES = 3

DRIVER_DIR = "data/drivers"
DRIVER_LOG_PATH = DRIVER_DIR + "/crawl.tsv"

RACE_RESULTS_DIR = "data/race_results"
RACE_RESULTS_LOG_PATH = RACE_RESULTS_DIR + "/crawl.tsv"

# Fetch a page and save it to path if the status is 200.
# Retries on network errors and on 429/5xx; returns None if every attempt failed.
def fetch_and_save(url, path):
    # Retry mechanism
    for attempt in range(RETRIES):
        try:
            # Fetch URL
            response = requests.get(url, headers=HEADERS, timeout=10)
            # If 200 save HTML file and return response
            if response.status_code == 200:
                with open(path, "wb") as f:
                    f.write(response.content)
                print("\t\t" + str(response.status_code), len(response.content), "bytes ->", path)
                return response
            # If 429 or 5xx, retry, else log the status and return response
            if response.status_code != 429 and response.status_code < 500:
                print(f"\t\tStatus {response.status_code} for {url}")
                return response
            print(f"\t\tAttempt {attempt + 1} failed with status code {response.status_code}. Retrying...")
        except requests.RequestException as e:
            print(f"\t\tAttempt {attempt + 1} failed with error: {e}")
        # Exponential backoff
        if attempt < RETRIES - 1:
            time.sleep(2 * 2 ** attempt)  
    return None

# Find all driver slugs in the HTML content of the standings page
def find_driver_slugs(html):
    # set takes care of duplicates
    slugs = set(re.findall(r'profile_url\\":\\"/drivers/([a-z0-9-]+)', html))
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

# Log crawled driver slug 
def log_page(log_path, status, key, path, url):
    new_file = not os.path.exists(log_path)
    with open(log_path, "a", encoding="utf-8") as f:
        if new_file:
            f.write("status\tkey\tpath\turl\n")
        driver_log = [status, str(key), path, url]
        f.write("\t".join(driver_log) + "\n")

# Load already crawled drivers
def load_done(log_path):
    done = set()
    # If no file exists, no crawled drivers
    if not os.path.exists(log_path):
        return done
    with open(log_path, encoding="utf-8") as f:
        next(f)  # skip header
        # Check if key is already in logs
        for line in f:
            status, key = line.strip().split("\t")[:2]
            if status == "200":
                done.add(key)
    return done

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
        print(f"\tCrawling standings for {year}...\n")
        response = fetch_and_save(url, path)
        if response is None or response.status_code != 200:
            if response is None:
                status = "\tNo response"
            else:
                status = response.status_code
            print(f"\tFailed to fetch standings for {year}. Status code: {status}")
        time.sleep(2)

# Crawl all drivers given a list of (index, slug) tuples
def crawl_drivers(slugs):
    print("===Crawling drivers...===")
    # Create dir
    os.makedirs(DRIVER_DIR, exist_ok=True)
    # Load already crawled drivers
    done_drivers = load_done(DRIVER_LOG_PATH)
    for index, slug in slugs:
        # Construct URL
        driver_url = f"{BASE_URL}/drivers/{slug}"
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

def find_round_numbers(html, year):
    pattern = rf'href="/championships/formula-1/{year}/results/round-(\d+)"'
    rounds = set(re.findall(pattern, html))
    round_numbers = []
    for r in rounds:
        round_numbers.append(int(r))
    return sorted(round_numbers)

# Crawl all drivers given a list of (index, slug) tuples
def crawl_race_results(race_numbers, year):
    print(f"===Crawling race results for {year}...===")
    # Create dir
    os.makedirs(RACE_RESULTS_DIR, exist_ok=True)
    doe_race_results = load_done(RACE_RESULTS_LOG_PATH)
    for index, number in race_numbers:
        key = f"{year}-round-{number}"
        # Construct URL
        race_url = f"{BASE_URL}/championships/formula-1/{year}/results/round-{number}/race-1"
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

def crawl_all_race_results():
    print("===Crawling race results for all years...===\n")
    for year in YEARS:
        path = os.path.join(CALENDAR_DIR, f"{year}-calendar.html")
        # Skip seasons whose standings failed to download
        if not os.path.exists(path):
            print(f"\tCalendar for {year} not found. Skipping.")
            continue

        with open(path, "r", encoding="utf-8") as f:
            html = f.read()

        round_numbers = find_round_numbers(html, year)
        print(f"\tFound {len(round_numbers)} rounds for {year}.")
        round_numbers_with_index = list(enumerate(round_numbers))
        crawl_race_results(round_numbers_with_index, year)

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
    print(f"\n===DRIVERS - Finished in {hours} h {minutes} min {seconds} s===" + "\n")

    # Crawl calendars and race results
    start = time.time()
    crawl_calendars()
    crawl_all_race_results()

    # Elapsed time for race results
    elapsed = time.time() - start
    hours = int(elapsed // 3600)
    minutes = int(elapsed % 3600 // 60)
    seconds = int(elapsed % 60)
    print(f"\n===RACE RESULTS - Finished in {hours} h {minutes} min {seconds} s===")

    # Total elapsed time
    total_elapsed = time.time() - total_start
    total_hours = int(total_elapsed // 3600)
    total_minutes = int(total_elapsed % 3600 // 60)
    total_seconds = int(total_elapsed % 60)
    print(f"\n===TOTAL - Finished in {total_hours} h {total_minutes} min {total_seconds} s===" + "\n")