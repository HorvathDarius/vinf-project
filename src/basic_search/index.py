import json
import os
import re
import unicodedata
from extraction.extract import EXTRACTORS

INDEX_DIR = "index"
INDEX_PATH = INDEX_DIR + "/index.json"

# Token = run of lowercase letters and digits
TOKEN_RE = re.compile(r"[a-z0-9]+")
# Common English words that carry no meaning for search
STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "for", "from", "had", "has", "have", 
    "he", "his", "in", "into", "is", "it", "its", "of", "on", "or", "she", "that", "the", "their",
    "them", "they", "this", "to", "was", "were", "which", "who", "with"
}

# Lowercase, strip diacritics, split to words, drop stop words
def tokenize(text):
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return [token for token in TOKEN_RE.findall(text) if token not in STOP_WORDS]

# Title shown in search results
def doc_title(doc):
    if doc["type"] == "race_result":
        return f"{doc['year']} {doc['name']}"
    return doc.get("title") or doc.get("name") or doc["id"]

# Read all extracted JSONL files into one list of documents
def load_documents():
    docs = []
    for label, log_path, jsonl_path, extract_page, page_text in EXTRACTORS:
        with open(jsonl_path, "r", encoding="utf-8") as f:
            for line in f:
                doc = json.loads(line)
                doc["title"] = doc_title(doc)
                docs.append(doc)
    return docs


# Length of the main layout: first one named "Grand Prix", otherwise first with a length
def main_layout_length(layouts):
    with_length = [layout for layout in layouts if layout["length_meters"]]
    for layout in with_length:
        if layout["name"] and "grand prix" in layout["name"].lower():
            return f"{layout['length_meters']} m"
    if with_length:
        return f"{with_length[0]['length_meters']} m"
    return None

# Key facts under a search result, depending on document type
def doc_fields(doc):
    if doc["type"] == "driver":
        stats = doc["f1_stats"]
        born = " ".join(part for part in [doc["birth_date"], doc["place_of_birth"]] if part)
        return {
            "nationality": doc["nationality"],
            "born": born or None,
            "titles": ", ".join(str(year) for year in doc["f1_titles"]) or None,
            "races": stats.get("races"),
            "wins": stats.get("wins"),
        }
    if doc["type"] in ("race_result", "race_report"):
        return {
            "date": doc["date"],
            "track": doc["track"],
            "winner": doc["winner"],
        }
    if doc["type"] == "team":
        return {
            "country": doc["country"],
            "headquarters": doc["headquarters"],
            "principal": doc["principal"],
        }
    if doc["type"] == "track":
        return {
            "country": doc["country"],
            "length": main_layout_length(doc["layouts"]),
        }

# Inverted index: term -> doc_id -> term frequency
def build_index(docs):
    index = {}
    doc_lengths = {}
    for doc in docs:
        tokens = tokenize(doc["text"])
        doc_lengths[doc["id"]] = len(tokens)
        for token in tokens:
            postings = index.setdefault(token, {})
            postings[doc["id"]] = postings.get(doc["id"], 0) + 1
    return index, doc_lengths

# Save the index with document metadata (shown in results) to index/index.json
def save_index(docs, index, doc_lengths):
    os.makedirs(INDEX_DIR, exist_ok=True)
    data = {
        "N": len(docs),
        "docs": {
            doc["id"]: {
                "type": doc["type"], 
                "title": doc["title"], 
                "url": doc["source_url"],
                "fields": doc_fields(doc),
                "text": doc["text"]
            } for doc in docs
        },
        "doc_lengths": doc_lengths,
        "index": index
    }
    with open(INDEX_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)

# Print index size and the most common terms by document frequency
def index_stats(index, doc_lengths):
    total_tokens = sum(doc_lengths.values())
    postings = sum(len(p) for p in index.values())
    print(f"===Index: {len(doc_lengths)} documents, {len(index)} terms, {total_tokens} tokens, "
          f"avg {total_tokens / len(doc_lengths):.0f} tokens/doc, {postings} postings===")
    top = sorted(index.items(), key = lambda item: len(item[1]), reverse=True)[:10]
    print("Most common terms (df):", ", ".join(f"{term} {len(p)}" for term, p in top))

# Build the whole index: load documents, index them, save, print stats
def build():
    docs = load_documents()
    index, doc_lengths = build_index(docs)
    save_index(docs, index, doc_lengths)
    index_stats(index, doc_lengths)

if __name__ == "__main__":
    build()
