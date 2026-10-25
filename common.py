import requests
import os
import time

HEADERS = {"User-Agent": "VINF-F1-crawler/0.1 (FIIT STU student project)"}
RETRIES = 3


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

# Log crawled slug 
def log_page(log_path, status, key, path, url):
    new_file = not os.path.exists(log_path)
    with open(log_path, "a", encoding="utf-8") as f:
        if new_file:
            f.write("status\tkey\tpath\turl\n")
        doc_log = [status, str(key), path, url]
        f.write("\t".join(doc_log) + "\n")

# Load already crawled slugs from log file and return a set of keys
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

def print_elapsed_time(label, start):
    elapsed = time.time() - start
    hours = int(elapsed // 3600)
    minutes = int((elapsed % 3600) // 60)
    seconds = int(elapsed % 60)
    print(f"==={label} - Finished in {hours}h {minutes}m {seconds}s===\n")