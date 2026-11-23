import json
import os
import re
import time
import lucene
from java.nio.file import Paths
from java.util import Arrays
from org.apache.lucene.analysis import Analyzer, CharArraySet, LowerCaseFilter, StopFilter
from org.apache.lucene.analysis.miscellaneous import ASCIIFoldingFilter
from org.apache.lucene.analysis.standard import StandardTokenizer
from org.apache.lucene.document import Document, Field, IntField, StringField, TextField
from org.apache.lucene.index import DirectoryReader, IndexWriter, IndexWriterConfig
from org.apache.lucene.store import FSDirectory
from org.apache.pylucene.analysis import PythonAnalyzer
from common import print_elapsed_time
from basic_search.index import STOP_WORDS, doc_title

# Output folder of the Spark jobs: our documents and their joined wiki data
SPARK_DIR = "extracted_spark"
# Document type = (our documents, joined wiki data)
INPUT_FILES = {
    "driver": ("drivers.jsonl", "wiki_drivers.jsonl"),
    "race_result": ("race_results.jsonl", "wiki_race_results.jsonl"),
    "race_report": ("race_reports.jsonl", "wiki_race_reports.jsonl"),
    "track": ("tracks.jsonl", "wiki_tracks.jsonl"),
    "team": ("teams.jsonl", "wiki_teams.jsonl"),
}
# Lucene index folder (the old index stays in index/index.json)
LUCENE_INDEX_DIR = "index/lucene"
# Date in our documents: 1951-05-27
DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")

# Read a JSONL file into a list of records
def read_jsonl(file_name):
    with open(os.path.join(SPARK_DIR, file_name), "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f]

# Our documents by id, each with the wiki title and wiki attributes if the join matched it
def load_documents():
    docs = {}
    for doc_type, (docs_file, wiki_file) in INPUT_FILES.items():
        for doc in read_jsonl(docs_file):
            doc["title"] = doc_title(doc)
            docs[doc["id"]] = doc
        for joined in read_jsonl(wiki_file):
            doc = docs[joined["id"]]
            doc["wiki_title"] = joined["wiki_title"]
            doc["wiki"] = joined["wiki"]
    return docs

# Documents and wiki matches per type, and the wiki keys of one document of each type
def print_documents_stats(docs):
    for doc_type in INPUT_FILES:
        of_type = [doc for doc in docs.values() if doc["type"] == doc_type]
        with_wiki = [doc for doc in of_type if "wiki" in doc]
        print("==={:<12} {:>5} / {:>5} with wiki data===".format(doc_type, len(with_wiki), len(of_type)))
        if with_wiki:
            print("    our keys:  {}".format(", ".join(with_wiki[0].keys())))
            print("    wiki keys: {}".format(", ".join(with_wiki[0]["wiki"].keys())))
    with_wiki_count = sum(1 for doc in docs.values() if "wiki" in doc)
    print("===Total: {} / {} documents with wiki data===".format(with_wiki_count, len(docs)))

# === ANALYZER ===

# Same steps as tokenize() of the old index: split to words, lowercase, strip diacritics, drop stop words
class F1Analyzer(PythonAnalyzer):
    def __init__(self):
        super().__init__()
        self.stop_words = CharArraySet(Arrays.asList(sorted(STOP_WORDS)), True)

    def createComponents(self, field_name):
        tokenizer = StandardTokenizer()
        stream = LowerCaseFilter(tokenizer)
        stream = ASCIIFoldingFilter(stream)
        stream = StopFilter(stream, self.stop_words)
        return Analyzer.TokenStreamComponents(tokenizer, stream)



# === FIELDS ===

# Analyzed text, searchable by words and phrases
def add_text(document, name, value, stored=False):
    if value:
        store = Field.Store.YES if stored else Field.Store.NO
        document.add(TextField(name, str(value), store))

# Exact value, lowercased, for filters like nationality:finnish
def add_keyword(document, name, value):
    if value:
        document.add(StringField(name, str(value).lower(), Field.Store.YES))

# Number, searchable by range like wins:[20 TO *]
def add_int(document, name, value):
    if value is not None:
        document.add(IntField(name, int(value), Field.Store.YES))

# 1951-05-27 -> 19510527, so dates can be compared as numbers
def date_number(date):
    match = DATE_RE.match(date or "")
    return int("".join(match.groups())) if match else None

# Fields of every document: id, type, name, our text and the wiki texts
def add_common_fields(document, doc, wiki):
    document.add(StringField("id", doc["id"], Field.Store.YES))
    document.add(StringField("type", doc["type"], Field.Store.YES))
    add_text(document, "title", doc["title"], stored=True)
    add_text(document, "text", doc["text"], stored=True)
    add_text(document, "wiki_title", doc.get("wiki_title"), stored=True)
    add_text(document, "wiki_abstract", wiki.get("abstract"), stored=True)
    add_text(document, "wiki_text", wiki.get("text"))
    add_text(document, "wiki_categories", " | ".join(wiki.get("categories") or []))

# Driver: nationality filter, numbers from our f1_stats (complete), teams from wiki
def add_driver_fields(document, doc, wiki):
    add_keyword(document, "nationality", doc["nationality"])
    birth_date = date_number(doc["birth_date"])
    add_int(document, "birth_year", birth_date // 10000 if birth_date else None)
    for stat in ("races", "wins", "podiums", "poles"):
        add_int(document, stat, doc["f1_stats"].get(stat))
    add_int(document, "titles", len(doc["f1_titles"]))
    for year in doc["f1_titles"]:
        add_int(document, "title_year", year)
    add_text(document, "teams", wiki.get("teams"))

# Race result and race report: year and date ranges, winner and track phrases, more facts from wiki
def add_race_fields(document, doc, wiki):
    add_int(document, "year", doc["year"])
    add_int(document, "date", date_number(doc["date"]))
    add_text(document, "winner", doc["winner"], stored=True)
    add_text(document, "track", doc["track"], stored=True)
    add_text(document, "pole_driver", wiki.get("pole_driver"))
    add_text(document, "winner_team", wiki.get("winner_team"))
    add_int(document, "laps", wiki.get("laps"))

# Track: country filter, length, turns and opening year from wiki
def add_track_fields(document, doc, wiki):
    add_keyword(document, "country", doc["country"])
    length_km = wiki.get("length_km")
    add_int(document, "length_m", round(length_km * 1000) if length_km else None)
    add_int(document, "turns", wiki.get("turns"))
    add_int(document, "opened", wiki.get("opened"))

# Team: country filter, wins and titles from wiki (only matched teams have them)
def add_team_fields(document, doc, wiki):
    add_keyword(document, "country", doc["country"])
    add_int(document, "wins", wiki.get("wins"))
    add_int(document, "constructors_titles", wiki.get("constructors_titles"))

# Document type -> function adding its own fields
TYPE_FIELDS = {
    "driver": add_driver_fields,
    "race_result": add_race_fields,
    "race_report": add_race_fields,
    "track": add_track_fields,
    "team": add_team_fields,
}

# One of our documents (with its wiki data) as a Lucene document
def to_lucene_document(doc):
    wiki = doc.get("wiki") or {}
    document = Document()
    add_common_fields(document, doc, wiki)
    TYPE_FIELDS[doc["type"]](document, doc, wiki)
    return document



# === INDEX ===

# Write all documents into a new Lucene index (an existing one is replaced)
def build_index(docs):
    config = IndexWriterConfig(F1Analyzer())
    config.setOpenMode(IndexWriterConfig.OpenMode.CREATE)
    writer = IndexWriter(FSDirectory.open(Paths.get(LUCENE_INDEX_DIR)), config)
    for doc in docs.values():
        writer.addDocument(to_lucene_document(doc))
    writer.commit()
    writer.close()

# Read the index back and print how many documents it holds
def print_index_stats():
    reader = DirectoryReader.open(FSDirectory.open(Paths.get(LUCENE_INDEX_DIR)))
    print("===Lucene index: {} documents in {}===".format(reader.numDocs(), LUCENE_INDEX_DIR))
    reader.close()

def main():
    lucene.initVM()
    start = time.time()
    docs = load_documents()
    print_documents_stats(docs)
    print_elapsed_time("LOAD DOCUMENTS", start)

    start = time.time()
    build_index(docs)
    print_index_stats()
    print_elapsed_time("LUCENE INDEX", start)

if __name__ == "__main__":
    main()