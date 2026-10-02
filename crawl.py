import requests
import re
import os
import time

HEADERS = {"User-Agent": "VINF-F1-crawler/0.1 (FIIT STU student project)"}
BASE_URL = "https://www.driverdb.com"
STANDINGS_URL = BASE_URL + "/championships/formula-1/2026/standings"

LOG_PATH = "data/drivers/crawl.tsv"

# Fetch and save the standings page to a local file
def fetch_and_save(url, path):
    response = requests.get(url, headers=HEADERS, timeout=10)
    with open(path, "wb") as f:
        f.write(response.content)
    print(response.status_code, len(response.content), "bytes ->", path)
    return response

# Find all driver slugs in the HTML content of the standings page
def find_driver_slugs(html):
    # set takes care of duplicates
    slugs = set(re.findall(r'/drivers/([a-z0-9-]+)', html))
    slugs.discard("profile")
    return sorted(slugs)

# fetch_and_save(STANDINGS_URL, "standings.html")
slugs = find_driver_slugs(open("standings.html", "r", encoding="utf-8").read())
print(len(slugs))
print(slugs)
slugs = [(slug, i) for i, slug in enumerate(slugs)]

def log_driver_slug(slug, status, path):
    new_file = not os.path.exists(LOG_PATH)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        if new_file:
            f.write("url\tstatus\tpath\n")
        driver_log = [slug, status, path]
        f.write("\t".join(driver_log) + "\n")

def load_done_drivers(log_path):
    done_drivers = set()
    if not os.path.exists(log_path):
        return done_drivers
    with open(log_path, encoding="utf-8") as f:
        next(f)  # skip header
        for line in f:
            slug, status = line.strip().split("\t")[:2]
            if status == "200":
                done_drivers.add(slug)
    return done_drivers

def crawl_drivers(slugs):
    os.makedirs("data/drivers", exist_ok=True)
    done_drivers = load_done_drivers(LOG_PATH)
    for slug, index in slugs:
        driver_url = f"{BASE_URL}/drivers/{slug}"
        if driver_url in done_drivers:
            print("Skipping driver:", slug, "(", index + 1, "/", len(slugs), ")")
            continue
        print ("Crawling driver:", slug, "(", index + 1, "/", len(slugs), ")")
        response = fetch_and_save(driver_url, f"data/drivers/{slug}.html")
        log_driver_slug(driver_url, str(response.status_code), f"data/drivers/{slug}.html")
        time.sleep(2)

crawl_drivers(slugs)