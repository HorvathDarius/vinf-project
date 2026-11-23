import sys
import lucene
from lucene import JArray
from java.lang import Float, Integer
from java.nio.file import Paths
from java.text import NumberFormat
from java.util import HashMap, Locale
from org.apache.lucene.analysis import Analyzer, LowerCaseFilter
from org.apache.lucene.analysis.core import KeywordTokenizer
from org.apache.lucene.analysis.miscellaneous import PerFieldAnalyzerWrapper
from org.apache.lucene.index import DirectoryReader
from org.apache.lucene.queryparser.flexible.standard import StandardQueryParser
from org.apache.lucene.queryparser.flexible.standard.config import PointsConfig, StandardQueryConfigHandler
from org.apache.lucene.search import IndexSearcher
from org.apache.lucene.search.highlight import Highlighter, QueryScorer, SimpleHTMLFormatter
from org.apache.lucene.search.similarities import BM25Similarity
from org.apache.lucene.store import FSDirectory
from org.apache.pylucene.analysis import PythonAnalyzer
from lucene_search.lucene_build import LUCENE_INDEX_DIR, F1Analyzer

# BM25 with the same parameters as the old search, so the comparison shows the index, not the scoring
K1 = 1.2
B = 0.75
# Fields searched when the query names no field, with boosts (a match in the name counts most)
DEFAULT_FIELDS = {
    "title": 3.0, "wiki_title": 2.0, "text": 1.0,
    "wiki_abstract": 1.0, "wiki_categories": 1.0, "wiki_text": 0.5,
}
# Exact-value fields (StringField): the query value is only lowercased, not split into words
KEYWORD_FIELDS = ["id", "type", "nationality", "country"]
# Number fields (IntField), searchable by ranges like wins:[20 TO *]
INT_FIELDS = [
    "birth_year", "races", "wins", "podiums", "poles", "titles", "title_year",
    "year", "date", "laps", "length_m", "turns", "opened", "constructors_titles",
]
# Fields shown under a result, depending on document type
SHOWN_FIELDS = {
    "driver": ["nationality", "birth_year", "races", "wins", "titles"],
    "race_result": ["date", "track", "winner"],
    "race_report": ["date", "track", "winner"],
    "track": ["country", "length_m", "turns", "opened"],
    "team": ["country", "wins", "constructors_titles"],
}
# Stored text fields used for the snippet, the first one with a query term wins
SNIPPET_FIELDS = ["text", "wiki_abstract"]
SNIPPET_CHARS = 160



# === SEARCHER ===

# Whole value as one lowercased term, same as add_keyword() stores it: "Great Britain" -> "great britain"
class KeywordAnalyzer(PythonAnalyzer):
    def createComponents(self, field_name):
        tokenizer = KeywordTokenizer()
        return Analyzer.TokenStreamComponents(tokenizer, LowerCaseFilter(tokenizer))

# Text fields use the index analyzer, keyword fields only lowercase the whole value
def query_analyzer():
    keyword = KeywordAnalyzer()
    per_field = HashMap()
    for field in KEYWORD_FIELDS:
        per_field.put(field, keyword)
    return PerFieldAnalyzerWrapper(F1Analyzer(), per_field)

# Query parser: default fields with boosts, OR between words (as the old search), number fields as points
def query_parser(analyzer):
    parser = StandardQueryParser(analyzer)
    # Same as parser.setMultiFields(), which PyLucene cannot call with a Python list
    multi_fields = StandardQueryConfigHandler.ConfigurationKeys.MULTI_FIELDS
    parser.getQueryConfigHandler().set(multi_fields, JArray("string")(list(DEFAULT_FIELDS)))
    boosts = HashMap()
    for field, boost in DEFAULT_FIELDS.items():
        boosts.put(field, Float(boost))
    parser.setFieldsBoost(boosts)
    points = HashMap()
    for field in INT_FIELDS:
        points.put(field, PointsConfig(NumberFormat.getIntegerInstance(Locale.ROOT), Integer.class_))
    parser.setPointsConfigMap(points)
    return parser

# Everything needed to answer queries, opened once
class LuceneSearcher:
    def __init__(self, index_dir=LUCENE_INDEX_DIR):
        self.reader = DirectoryReader.open(FSDirectory.open(Paths.get(index_dir)))
        self.searcher = IndexSearcher(self.reader)
        self.searcher.setSimilarity(BM25Similarity(K1, B))
        self.analyzer = query_analyzer()
        self.parser = query_parser(self.analyzer)

    # Parse the query text, words without a field go to DEFAULT_FIELDS; raises lucene.JavaError on a syntax error
    def parse(self, query_text):
        return self.parser.parse(query_text, None)

    # Top results as (score, stored document)
    def search(self, query, top_k=10):
        top = self.searcher.search(query, top_k)
        stored = self.searcher.storedFields()
        return top.totalHits.value(), [(hit.score, stored.document(hit.doc)) for hit in top.scoreDocs]

    # Best fragment of the first stored text field containing a query term, terms in [brackets]
    # QueryScorer(query, field) highlights only terms searched in that field, not filters like type:driver
    def snippet(self, query, document):
        for field in SNIPPET_FIELDS:
            text = document.get(field)
            if text:
                highlighter = Highlighter(SimpleHTMLFormatter("[", "]"), QueryScorer(query, field))
                fragment = highlighter.getBestFragment(self.analyzer, field, text)
                if fragment:
                    return fragment
        return None

    def close(self):
        self.reader.close()



# === OUTPUT ===

# 19510527 -> 1951-05-27
def format_date(number):
    return "{}-{}-{}".format(number[:4], number[4:6], number[6:])

# Key fields on one line, missing fields are skipped
def format_fields(document):
    shown = SHOWN_FIELDS.get(document.get("type"), [])
    values = []
    for field in shown:
        value = document.get(field)
        if value:
            values.append("{}: {}".format(field, format_date(value) if field == "date" else value))
    return " . ".join(values)

# Print ranked results with score, type, title, key fields and snippet
def print_results(lucene_searcher, query_text, top_k=10):
    try:
        query = lucene_searcher.parse(query_text)
    except lucene.JavaError as error:
        print("Invalid query: {}".format(error.getJavaException().getMessage()))
        return
    total, results = lucene_searcher.search(query, top_k)
    print("===Query: {} ({} hits)===".format(query_text, total))
    print("   Lucene query: {}".format(query))
    if not results:
        print("No results found.")
        return
    for rank, (score, document) in enumerate(results, start=1):
        print("{:>2}. {:7.3f} [{}] {}".format(rank, score, document.get("type"), document.get("title")))
        fields = format_fields(document)
        if fields:
            print("{:12}{}".format("", fields))
        snippet = lucene_searcher.snippet(query, document)
        if snippet:
            print("{:12}{}".format("", " ".join(snippet.split())[:SNIPPET_CHARS]))
        print()

# Read queries in a loop until :q
def interactive(lucene_searcher):
    print("F1 search (Lucene). Fields: title, text, winner, track, nationality, wins, year, ... :q to quit.")
    while True:
        try:
            line = input("f1 [lucene]> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if line in (":q", ":quit"):
            break
        if line:
            print_results(lucene_searcher, line)

# Search the query from the command line, or start interactive search without one
def main():
    lucene.initVM()
    lucene_searcher = LuceneSearcher()
    if len(sys.argv) > 1:
        print_results(lucene_searcher, " ".join(sys.argv[1:]))
    else:
        interactive(lucene_searcher)
    lucene_searcher.close()

if __name__ == "__main__":
    main()