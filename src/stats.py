import json
import os
import tiktoken
from extract import EXTRACTORS, read_crawled
from index import INDEX_PATH, tokenize
from crawl import STANDINGS_DIR, CALENDAR_DIR, TEAMS_BY_YEAR_DIR
from crawl_fansite import SITEMAPS_DIR

ENCODING = "cl100k_base" # tiktoken encoding used by GPT-4
# Column key -> header shown in the table
COLUMNS = {
    "pages": "Crawled pages",
    "html_mb": "HTML (MB)",
    "jsonl_mb": "Extracted (MB)",
    "docs": "Documents",
    "our_tokens": "Our tokens",
    "tiktoken_tokens": "Tiktoken tokens",
}
# Pages crawled only to find links, they are not indexed
HELPER_DIRS = [
    ("standings", STANDINGS_DIR),
    ("calendars", CALENDAR_DIR),
    ("teams_by_year", TEAMS_BY_YEAR_DIR),
    ("sitemaps", SITEMAPS_DIR),
]

# Size in MB
def megabytes(size):
    return size / (1024 * 1024)

# Statistics of one document type: crawled pages, HTML size, extracted documents and tokens
def type_stats(log_path, jsonl_path, encoder):
    pages = read_crawled(log_path)
    html_size = sum(os.path.getsize(path) for key, path, url in pages)
    docs = 0
    our_tokens = 0
    tiktoken_tokens = 0
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            text = json.loads(line)["text"]
            docs += 1
            our_tokens += len(tokenize(text))
            tiktoken_tokens += len(encoder.encode(text))
    return {
        "pages": len(pages),
        "html_mb": megabytes(html_size),
        "jsonl_mb": megabytes(os.path.getsize(jsonl_path)),
        "docs": docs,
        "our_tokens": our_tokens,
        "tiktoken_tokens": tiktoken_tokens,
    }

# Number of files and their total size in one directory
def dir_stats(directory):
    files = [os.path.join(directory, name) for name in os.listdir(directory)]
    files = [path for path in files if os.path.isfile(path)]
    return len(files), sum(os.path.getsize(path) for path in files)

# One table row, sizes with one decimal, counts with thousands separator
def print_row(label, stats, columns):
    cells = []
    for column in columns:
        value = stats[column]
        cells.append(f"{value:>17.1f}" if column.endswith("_mb") else f"{value:>17,}")
    print(f"{label:<14}" + "".join(cells))

# Print a table with stats
def print_stats():
    encoder = tiktoken.get_encoding(ENCODING)
    columns = list(COLUMNS)
    total = dict.fromkeys(columns, 0)
    header = f"{'Type':<14}" + "".join(f"{COLUMNS[column]:>17}" for column in columns)
    print(header)
    print("-" * len(header))
    for label, log_path, jsonl_path, extract_page, page_text in EXTRACTORS:
        stats = type_stats(log_path, jsonl_path, encoder)
        for column in columns:
            total[column] += stats[column]
        print_row(label, stats, columns)
    print("-" * len(header))
    print_row("Total", total, columns)

    print("\nHelper pages (only link sources, not indexed)")
    helper_header = f"{'Type':<14}{COLUMNS['pages']:>17}{COLUMNS['html_mb']:>17}"
    print(helper_header)
    print("-" * len(helper_header))
    helper_pages = 0
    helper_size = 0
    for label, directory in HELPER_DIRS:
        pages, size = dir_stats(directory)
        helper_pages += pages
        helper_size += size
        print(f"{label:<14}{pages:>17,}{megabytes(size):>17.1f}")
    print("-" * len(helper_header))
    print(f"{'Total':<14}{helper_pages:>17,}{megabytes(helper_size):>17.1f}")

    crawled_pages = total["pages"] + helper_pages
    crawled_mb = total["html_mb"] + megabytes(helper_size)
    print(f"\nAll crawled: {crawled_pages:,} pages, {crawled_mb:.1f} MB")
    print(f"Index: {megabytes(os.path.getsize(INDEX_PATH)):.1f} MB, tiktoken encoding: {ENCODING}")

if __name__ == "__main__":
    print_stats()