import json
import os 
from pyspark.sql import SparkSession
from extract import EXTRACTORS, read_crawled

# One partition per core of the local machine (12 cores)
PARTITIONS = 12
# Label -> function that extracts a page and build its searchable text
EXTRACTOR_BY_LABEL = {
    label: (extract_page, page_text)
    for label, log_path, jsonl_path, extract_page, page_text in EXTRACTORS
}
# Outout dir
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

# Extract all crawled pages in parallel with Spark into extracted_spark/<type>.jsonl
def main():
    spark = SparkSession.builder.appName("vinf-extract").getOrCreate()
    tasks = build_tasks()
    print("===Extracting {} pages with Spark ({} partitions)".format(len(tasks), PARTITIONS))
    pages = spark.sparkContext.parallelize(tasks, PARTITIONS).map(extract_task).cache()
    for label, log_path, jsonl_path, extract_page, page_text in EXTRACTORS:
        lines = pages.filter(lambda record, label=label: record[0] == label).map(lambda record: record[1]).collect()
        out_path = write_jsonl(lines, jsonl_path)
        print("===Extracted {} {} to {}".format(len(lines), label, out_path))
    spark.stop()

if __name__ == "__main__":
    main()
