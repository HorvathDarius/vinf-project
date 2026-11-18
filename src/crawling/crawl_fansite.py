import os
import time
import re
from common import fetch_and_save, log_page, load_done, print_elapsed_time, crawl_delay

BASE_URL = "https://www.f1-fansite.com"
YEARS = range(1950, 2027)

# Words in the slug that mark a non-race post (qualifying, practice, sprint, tests...)
EXCLUDED_WORDS = ["quali", "grid", "practice", "lap-times", "sprint", "test"]

# DIRS
SITEMAPS_DIR = "data/fansite_sitemaps"
RACE_REPORTS_DIR = "data/fansite_race_reports"

# URLS
SITEMAP_URL = BASE_URL + "/sitemap-posttype-post.{year}.xml"

# LOGS
RACE_REPORTS_LOG_PATH = RACE_REPORTS_DIR + "/crawl.tsv"

# Crawl post sitemaps for all years and save them to files
def crawl_sitemaps():
    print("===Crawling sitemaps for all years...===")
    os.makedirs(SITEMAPS_DIR, exist_ok=True)
    for year in YEARS:
        url = SITEMAP_URL.format(year=year)
        path = os.path.join(SITEMAPS_DIR, f"{year}-sitemap.xml")
        # Skip if file already exists
        if os.path.exists(path):
            print(f"\tSitemap for {year} already exists. Skipping.")
            continue
        print(f"\tCrawling sitemap for {year}...")
        response = fetch_and_save(url, path)
        if response is None or response.status_code != 200:
            if response is None:
                status = "No response"
            else:
                status = response.status_code
            print(f"\tFailed to fetch sitemap for {year}. Status code: {status}")
        time.sleep(crawl_delay(url))

# Find all race report URLs in the sitemap XML
def find_race_report_urls(xml):
    pattern = r'<loc>(https://www\.f1-fansite\.com/f1-result/[^<]+)</loc>'
    urls = set(re.findall(pattern, xml))
    race_urls = []
    for url in urls:
        slug = url.split("/f1-result/")[1]
        # Skip non-race posts
        if any(word in slug for word in EXCLUDED_WORDS):
            continue
        # Skip practice posts named fp1, fp2, fp3
        if re.search(r'fp\d', slug):
            continue
        race_urls.append(url)
    return sorted(race_urls)


# Find all race report URLs across all sitemaps and return a sorted list of (year, url)
def collect_race_report_urls():
    print("===Collecting race report URLs for all years...===")
    all_urls = []
    for year in YEARS:
        path = os.path.join(SITEMAPS_DIR, f"{year}-sitemap.xml")
        # Skip years whose sitemap failed to download
        if not os.path.exists(path):
            print(f"\tSitemap for {year} not found. Skipping.")
            continue

        with open(path, "r", encoding="utf-8") as f:
            xml = f.read()

        urls = find_race_report_urls(xml)
        print(f"\tFound {len(urls)} race reports for {year}.")
        for url in urls:
            slug = url.split("/f1-result/")[1]
            # Prefer the season year in the slug, the sitemap year is the publish year
            match = re.search(r'(19|20)\d{2}', slug)
            if match:
                race_year = int(match.group())
            else:
                race_year = year
            all_urls.append((race_year, url))
    return all_urls

# Crawl all race reports given a list of (index, (year, url)) tuples
def crawl_race_reports(race_urls):
    print("===Crawling race reports...===")
    # Create dir
    os.makedirs(RACE_REPORTS_DIR, exist_ok=True)
    done_reports = load_done(RACE_REPORTS_LOG_PATH)
    for index, (year, url) in race_urls:
        # Slug without the trailing slash is the key
        key = url.split("/f1-result/")[1].strip("/")
        path = f"{RACE_REPORTS_DIR}/{year}-{key}.html"
        # If key in LOG, then skip
        if key in done_reports:
            print(f"\tSkipping race report: {key} ({index + 1}/{len(race_urls)})")
            continue
        # Else crawl
        print(f"\tCrawling race report: {key} ({index + 1}/{len(race_urls)})")
        response = fetch_and_save(url, path)
        if response is None:
            status = "error"
        else:
            status = str(response.status_code)
        log_page(RACE_REPORTS_LOG_PATH, status, key, path, url)
        time.sleep(crawl_delay(url))

def crawl_f1_fansite():
    start = time.time()

    crawl_sitemaps()
    race_urls = collect_race_report_urls()
    print(f"===Found {len(race_urls)} race reports across all years.===\n")
    race_urls_with_index = list(enumerate(race_urls))
    crawl_race_reports(race_urls_with_index)

    # Elapsed time for race reports
    print_elapsed_time("RACE REPORTS", start)

if __name__ == "__main__":
    crawl_f1_fansite()
