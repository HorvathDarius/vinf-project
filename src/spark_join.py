import datetime
import json
import math
import os
import re
import time
from pyspark.sql import SparkSession
from common import print_elapsed_time
from index import tokenize

# Inputs: our extracted documents (step 1) and wiki entities + redirects (step 2)
OUR_JSONL = "extracted_spark/*.jsonl"
ENTITIES_JSONL = "wiki_spark/entities.jsonl"
REDIRECTS_JSONL = "wiki_spark/redirects.jsonl"
# Output: one file per type, our document id + matched wiki page and its attributes
JOINED_DIR = "extracted_spark"
# Our document type -> wiki entity type
WIKI_TYPE = {"driver": "driver", "race_result": "race", "race_report": "race", "track": "track", "team": "team"}
# Our type -> output file
JOINED_FILES = {
    "driver": "wiki_drivers.jsonl", "race_result": "wiki_race_results.jsonl", "race_report": "wiki_race_reports.jsonl",
    "track": "wiki_tracks.jsonl", "team": "wiki_teams.jsonl",
}
# Match methods from the most to the least reliable
METHODS = ["verified", "name", "date"]
# Tracks closer than this are the same place
TRACK_DISTANCE_KM = 5
# Words of our race names that are not in wiki titles: "Azerbaijan F1 Grand Prix" -> "Azerbaijan Grand Prix"
RACE_NOISE_RE = re.compile(r'\b(?:F1|Formula 1|Formula One)\b', re.IGNORECASE)
PARENTHESES_RE = re.compile(r'\(.*?\)')



# === KEYS ===

# Name key: no disambiguation in parentheses, lowercase, no diacritics, no stop words
# "Nelson Piquet (racing driver)" -> "nelson piquet", "Kimi Räikkönen" -> "kimi raikkonen"
def name_key(name):
    if not name:
        return None
    return " ".join(tokenize(PARENTHESES_RE.sub(" ", name))) or None

# Date shifted by days, f1-fansite dates some reports one day after the race
def shift_date(date, days):
    day = datetime.datetime.strptime(date, "%Y-%m-%d") + datetime.timedelta(days=days)
    return day.strftime("%Y-%m-%d")

# Join keys of our document: (key type, value)
def doc_keys(doc):
    doc_type = doc["type"]
    keys = []
    if doc_type == "driver":
        keys.append(("driver", name_key(doc["name"])))
    elif doc_type in ("race_result", "race_report"):
        if doc.get("date"):
            keys.extend(("race_date", shift_date(doc["date"], days)) for days in (-1, 0, 1))
        event = doc.get("name") if doc_type == "race_result" else doc.get("event")
        if event and doc.get("year"):
            keys.append(("race", name_key("{} {}".format(doc["year"], RACE_NOISE_RE.sub(" ", event)))))
    elif doc_type == "track":
        keys.append(("track", name_key(doc["name"])))
        keys.append(("track", name_key(doc["id"].split(":", 1)[1].replace("-", " "))))
    elif doc_type == "team":
        keys.append(("team", name_key(doc["name"])))
        keys.append(("team", name_key(doc.get("full_name"))))
        keys.append(("team", name_key(doc["id"].split(":", 1)[1].replace("-", " "))))
    return [key for key in keys if key[1]]

# Join keys of a wiki entity: its title, races also their date
def entity_keys(entity):
    keys = [(entity["type"], name_key(entity["title"]))]
    if entity["type"] == "race" and entity.get("date"):
        keys.append(("race_date", entity["date"]))
    return [key for key in keys if key[1]]



# === VERIFICATION ===

# Distance of two points on Earth in km (haversine)
def distance_km(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(math.radians, (lat1, lon1, lat2, lon2))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))

def track_distance(doc, entity):
    if doc.get("latitude") is None or not entity.get("coordinates"):
        return None
    return distance_km(doc["latitude"], doc["longitude"], entity["coordinates"][0], entity["coordinates"][1])

# How well a candidate wiki entity fits our document: verified by a second attribute, by name, or by date only
def match_method(doc, entity):
    doc_type = doc["type"]
    if doc_type == "driver":
        return "verified" if doc.get("birth_date") and doc["birth_date"] == entity.get("birth_date") else "name"
    if doc_type in ("race_result", "race_report"):
        same_winner = name_key(doc.get("winner")) is not None and name_key(doc.get("winner")) == name_key(entity.get("winner"))
        same_date = doc.get("date") is not None and doc["date"] == entity.get("date")
        if same_winner:
            return "verified"
        if same_date:
            return "date"
        same_name = doc.get("year") == entity.get("year")
        return "name" if same_name and entity.get("date") is None else None  # shifted date without the same winner is wrong
    if doc_type == "track":
        distance = track_distance(doc, entity)
        return "verified" if distance is not None and distance < TRACK_DISTANCE_KM else "name"
    return "name"

# Best candidate of a document: (method, title), None if no candidate fits
def best_match(doc, titles, entities):
    scored = []
    for title in set(titles):
        method = match_method(doc, entities[title])
        if method:
            scored.append((METHODS.index(method), title, method))
    if not scored:
        return None
    rank, title, method = min(scored)
    return method, title



# === JOIN ===

def read_jsonl(sc, path):
    return sc.textFile("file://" + os.path.abspath(path)).map(json.loads)

# Write records as JSON lines into one file
def write_jsonl(records, jsonl_path):
    os.makedirs(JOINED_DIR, exist_ok=True)
    with open(jsonl_path, "w", encoding="utf-8") as out:
        for record in records:
            out.write(json.dumps(record, ensure_ascii=False) + "\n")

# Joined record: our id, wiki title, how it matched and the wiki attributes (without type and title)
def joined_record(doc, match, entity):
    method, title = match
    wiki = {key: value for key, value in entity.items() if key not in ("type", "title")}
    return {"id": doc["id"], "type": doc["type"], "wiki_title": title, "match": method, "wiki": wiki}

def main():
    total_start = time.time()
    spark = SparkSession.builder.appName("vinf-join").getOrCreate()
    sc = spark.sparkContext

    docs = read_jsonl(sc, OUR_JSONL).filter(lambda doc: doc.get("type") in WIKI_TYPE).cache()
    entities = read_jsonl(sc, ENTITIES_JSONL).cache()
    redirects = read_jsonl(sc, REDIRECTS_JSONL)
    print("===Joining {} documents with {} wiki entities and {} redirects===".format(
        docs.count(), entities.count(), redirects.count()))

    # Wiki key table: (key type, key) -> title, from titles, race dates and redirects (aliases)
    start = time.time()
    title_types = entities.map(lambda entity: (entity["title"], entity["type"]))
    alias_keys = redirects.map(lambda redirect: (redirect["target"], redirect["title"])).join(title_types).map(lambda pair: ((pair[1][1], name_key(pair[1][0])), pair[0])).filter(lambda pair: pair[0][1])
    wiki_keys = entities.flatMap(lambda entity: [(key, entity["title"]) for key in entity_keys(entity)]).union(alias_keys).distinct()

    # Candidates: our document keys joined with the wiki keys of the same type
    our_keys = docs.flatMap(lambda doc: [(key, doc["id"]) for key in doc_keys(doc)])
    candidates = our_keys.join(wiki_keys).map(lambda pair: (pair[1][0], pair[1][1]))
    # Tracks also by coordinates: every track with every wiki track (87 x 212 pairs)
    wiki_tracks = entities.filter(lambda entity: entity["type"] == "track" and entity.get("coordinates"))
    near_tracks = docs.filter(lambda doc: doc["type"] == "track").cartesian(wiki_tracks).filter(lambda pair: (track_distance(pair[0], pair[1]) or TRACK_DISTANCE_KM) < TRACK_DISTANCE_KM).map(lambda pair: (pair[0]["id"], pair[1]["title"]))
    candidates = candidates.union(near_tracks).groupByKey().mapValues(list)

    # Left outer join: every document stays, unmatched ones get None
    entity_by_title = sc.broadcast(entities.map(lambda entity: (entity["title"], entity)).collectAsMap())
    joined = docs.map(lambda doc: (doc["id"], doc)).leftOuterJoin(candidates).map(lambda pair: (pair[1][0], best_match(pair[1][0], pair[1][1] or [], entity_by_title.value))).cache()
    results = joined.collect()
    print_elapsed_time("JOIN", start)

    # Output files and statistics
    all_titles = set()
    for doc_type, file_name in JOINED_FILES.items():
        of_type = [(doc, match) for doc, match in results if doc["type"] == doc_type]
        matched = [(doc, match) for doc, match in of_type if match]
        records = [joined_record(doc, match, entity_by_title.value[match[1]]) for doc, match in matched]
        write_jsonl(records, os.path.join(JOINED_DIR, file_name))
        titles = set(match[1] for doc, match in matched)
        all_titles |= titles
        methods = {method: sum(1 for doc, match in matched if match[0] == method) for method in METHODS}
        print("==={:<12} {:>5} docs, {:>5} matched ({:5.1f} %), {} unique wiki pages, {}===".format(
            doc_type, len(of_type), len(matched), 100.0 * len(matched) / max(len(of_type), 1), len(titles), methods))
    matched_count = sum(1 for doc, match in results if match)
    print("===Total: {} of {} documents matched, {} unique wiki pages===".format(matched_count, len(results), len(all_titles)))

    spark.stop()
    print_elapsed_time("JOIN TOTAL", total_start)

if __name__ == "__main__":
    main()