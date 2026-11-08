import json
import os
import time
from pyspark import StorageLevel
from pyspark.sql import SparkSession
from common import print_elapsed_time
import wiki

# Wikipedia dump: all 71 parts of enwiki-20261001-pages-articles (for development only part 1)
DUMP_FILES = "wiki_dump/*.bz2"
# DUMP_FILES = "wiki_dump/enwiki-20261001-pages-articles1.xml-p1p41242.bz2"
# Output folder of the wiki job
WIKI_DIR = "wiki_spark"
ENTITIES_JSONL = WIKI_DIR + "/entities.jsonl"
REDIRECTS_JSONL = WIKI_DIR + "/redirects.jsonl"
# One record = one <page>...</page>, one input split = one whole bz2 file (no splitting of compressed files)
HADOOP_CONF = {
    "textinputformat.record.delimiter": "</page>",
    "mapreduce.input.fileinputformat.split.minsize": str(10 ** 12),
}

# Redirect or F1 entity of one dump record as (kind, record), empty list if the page is not needed
def process_record(record):
    if "<ns>0</ns>" not in record:  # articles only, no talk/user/template pages
        return []
    if "<redirect" in record:
        page = wiki.parse_page(record)
        redirect = {"title": page["title"], "target": page["redirect"]}
        return [("redirect", redirect)]
    if "nfobox" not in record or not wiki.F1_MENTION_RE.search(record):  # cheap filter before parsing
        return []
    page = wiki.parse_page(record)
    doc_type = wiki.page_type(page["text"])
    if doc_type is None:
        return []
    return [("entity", wiki.wiki_entity(page, doc_type))]

# Write records as JSON lines into one file
def write_jsonl(records, jsonl_path):
    os.makedirs(WIKI_DIR, exist_ok=True)
    with open(jsonl_path, "w", encoding="utf-8") as out:
        for record in records:
            out.write(json.dumps(record, ensure_ascii=False) + "\n")

# Total size of files in MB
def size_mb(paths):
    return sum(os.path.getsize(path) for path in paths) / (1024 * 1024)

# Read the dump with Spark, keep F1 entities and the redirects pointing to them
def main():
    total_start = time.time()
    spark = SparkSession.builder.appName("vinf-wiki").getOrCreate()
    sc = spark.sparkContext
    dump_path = "file://" + os.path.abspath(DUMP_FILES)
    print("===Reading {}...===".format(dump_path))
    # Counts every <page> record read from the dump (filled on the workers)
    page_count = sc.accumulator(0)

    def count_and_process(record):
        page_count.add(1)
        return process_record(record)

    start = time.time()
    records = sc.newAPIHadoopFile(
        dump_path,
        "org.apache.hadoop.mapreduce.lib.input.TextInputFormat",
        "org.apache.hadoop.io.LongWritable",
        "org.apache.hadoop.io.Text",
        conf=HADOOP_CONF,
    ).map(lambda pair: pair[1])
    pages = records.flatMap(count_and_process).persist(StorageLevel.MEMORY_AND_DISK)

    entities = pages.filter(lambda page: page[0] == "entity").map(lambda page: page[1]).collect()
    write_jsonl(entities, ENTITIES_JSONL)
    for doc_type in ["driver", "race", "track", "team"]:
        count = sum(1 for entity in entities if entity["type"] == doc_type)
        print("===Entities {}: {}===".format(doc_type, count))
    print("===Read {} pages, extracted {} entities to {} ({:.1f} MB)===".format(
        page_count.value, len(entities), ENTITIES_JSONL, size_mb([ENTITIES_JSONL])))
    print_elapsed_time("WIKI ENTITIES", start)

    # Only redirects to our entities are needed for the join (aliases like Raikkonen -> Kimi Räikkönen)
    start = time.time()
    titles = sc.broadcast(set(entity["title"] for entity in entities))
    all_redirects = pages.filter(lambda page: page[0] == "redirect").map(lambda page: page[1])
    redirects = all_redirects.filter(lambda redirect: redirect["target"] in titles.value).collect()
    write_jsonl(redirects, REDIRECTS_JSONL)
    print("===Extracted {} of {} redirects to {} ({:.1f} MB)===".format(
        len(redirects), all_redirects.count(), REDIRECTS_JSONL, size_mb([REDIRECTS_JSONL])))
    print_elapsed_time("WIKI REDIRECTS", start)

    spark.stop()
    print_elapsed_time("WIKI TOTAL", total_start)

if __name__ == "__main__":
    main()