import json
import os
import time
from pyspark.sql import SparkSession
from common import print_elapsed_time
from extraction.extract import EXTRACTORS, read_crawled

# One partition per core of the local machine (12 cores)
PARTITIONS = 12
# Label -> function that extracts a page and build its searchable text
EXTRACTOR_BY_LABEL = {
    label: (extract_page, page_text)
    for label, log_path, jsonl_path, extract_page, page_text in EXTRACTORS
}
# Output dir
SPARK_EXTRACTED_DIR = "extracted_spark"

# All crawled pages of all types as (label, key, path, url) built in the driver
def build_tasks():
    tasks = []
    for label, log_path, jsonl_path, extract_page, page_text in EXTRACTORS:
        for key, path, url in read_crawled(log_path):
            tasks.append((label, key, path, url))
    return tasks

# Extract one page on a worker, same steps as extract_pages in part 1
def extract_task(task):
    label, key, path, url = task
    extract_page, page_text = EXTRACTOR_BY_LABEL[label]
    with open(path, "r", encoding="utf-8") as f:
        html = f.read()
    page = extract_page(html, key)
    page["source_url"] = url
    page["text"] = page_text(page)
    return label, json.dumps(page, ensure_ascii=False)

# Write JSON lines collected from the workers into one JSONL file
def write_jsonl(lines, jsonl_path):
    os.makedirs(SPARK_EXTRACTED_DIR, exist_ok=True)
    out_path = os.path.join(SPARK_EXTRACTED_DIR, os.path.basename(jsonl_path))
    with open(out_path, "w", encoding="utf-8") as out:
        for line in lines:
            out.write(line + "\n")
    return out_path

# Total size of files in MB
def size_mb(paths):
    return sum(os.path.getsize(path) for path in paths) / (1024 * 1024)

# Extract all crawled pages in parallel with Spark into extracted_spark/<type>.jsonl
def main():
    total_start = time.time()
    spark = SparkSession.builder.appName("vinf-extract").getOrCreate()
    tasks = build_tasks()
    print("===Extracting {} pages, {:.1f} MB of HTML with Spark ({} partitions)===".format(
        len(tasks), size_mb([path for label, key, path, url in tasks]), PARTITIONS))

    # count() runs the extraction of all pages once, the results stay in the cache
    start = time.time()
    pages = spark.sparkContext.parallelize(tasks, PARTITIONS).map(extract_task).cache()
    pages.count()
    print_elapsed_time("SPARK EXTRACT", start)

    start = time.time()
    for label, log_path, jsonl_path, extract_page, page_text in EXTRACTORS:
        lines = pages.filter(lambda record, label=label: record[0] == label).map(lambda record: record[1]).collect()
        out_path = write_jsonl(lines, jsonl_path)
        print("===Extracted {} {} to {} ({:.1f} MB)===".format(len(lines), label, out_path, size_mb([out_path])))
    print_elapsed_time("SPARK WRITE", start)

    spark.stop()
    print_elapsed_time("SPARK TOTAL", total_start)

if __name__ == "__main__":
    main()
