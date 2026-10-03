import sys
import requests
import re
import os
import time

HEADERS = {"User-Agent": "VINF-F1-crawler/0.1 (FIIT STU student project)"}
BASE_URL = "https://www.driverdb.com"
STANDINGS_URL = BASE_URL + "/championships/formula-1/2026/standings"

RETRIES = 3

LOG_PATH = "data/drivers/crawl.tsv"

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
                print(response.status_code, len(response.content), "bytes ->", path)
                return response
            # If 429 or 5xx, retry, else log the status and return response
            if response.status_code != 429 and response.status_code < 500:
                print(f"Status {response.status_code} for {url}")
                return response
            print(f"Attempt {attempt + 1} failed with status code {response.status_code}. Retrying...")
        except requests.RequestException as e:
            print(f"Attempt {attempt + 1} failed with error: {e}")
        # Exponential backoff
        if attempt < RETRIES - 1:
            time.sleep(2 * 2 ** attempt)  
    return None

# Find all driver slugs in the HTML content of the standings page
def find_driver_slugs(html):
    # set takes care of duplicates
    slugs = set(re.findall(r'/drivers/([a-z0-9-]+)', html))
    slugs.discard("profile")
    return sorted(slugs)

# Log crawled driver slug 
def log_driver_slug(status, slug, path, url):
    new_file = not os.path.exists(LOG_PATH)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        if new_file:
            f.write("status\tslug\tpath\turl\n")
        driver_log = [status, slug, path, url]
        f.write("\t".join(driver_log) + "\n")

# Load already crawled drivers
def load_done_drivers(log_path):
    done_drivers = set()
    # If no file exists, no crawled drivers
    if not os.path.exists(log_path):
        return done_drivers
    with open(log_path, encoding="utf-8") as f:
        next(f)  # skip header
        # Check if slug is already in logs
        for line in f:
            status, slug = line.strip().split("\t")[:2]
            if status == "200":
                done_drivers.add(slug)
    return done_drivers

# Crawl all drivers given a list of (index, slug) tuples
def crawl_drivers(slugs):
    # Create dir
    os.makedirs("data/drivers", exist_ok=True)
    # Load already crawled drivers
    done_drivers = load_done_drivers(LOG_PATH)
    for index, slug in slugs:
        # Construct URL
        driver_url = f"{BASE_URL}/drivers/{slug}"
        # If slug in LOG, then skip
        if slug in done_drivers:
            print("Skipping driver:", slug, "(", index + 1, "/", len(slugs), ")")
            continue
        # Else crawl
        print ("Crawling driver:", slug, "(", index + 1, "/", len(slugs), ")")
        response = fetch_and_save(driver_url, f"data/drivers/{slug}.html")
        if response is None:
            status = "error"
        else:
            status = str(response.status_code)
        log_driver_slug(status, slug, f"data/drivers/{slug}.html", driver_url)
        time.sleep(2)

if __name__ == "__main__":
    os.makedirs("data", exist_ok=True)

    response = fetch_and_save(STANDINGS_URL, "data/standings.html")

    if response is None or response.status_code != 200:
        print("Failed to fetch standings page. Exiting.")
        sys.exit(1)

    slugs = find_driver_slugs(response.text)
    slugs_with_index = list(enumerate(slugs))

    crawl_drivers(slugs_with_index)