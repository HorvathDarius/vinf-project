import json
import math
from basic_search.index import INDEX_PATH, tokenize

K1 = 1.2 # How fast repeated occurrences of a term stop adding score
B = 0.75 # How strongly long documents are penalized (0 = not at all, 1 = fully)
SNIPPET_WORDS = 20 # Number of words in snippet

# Load the index and precompute the collection statistics used by scoring
def load_index(path=INDEX_PATH):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    data["avg_length"] = sum(data["doc_lengths"].values()) / data["N"]
    data["max_df"] = max(len(postings) for postings in data["index"].values())
    return data

# Classic IDF: log(N / df)
def idf_classic(df, data):
    return math.log(data["N"] / df)

# IDF max: log(max_df / (1 + df)), relative to the most common term
def idf_max(df, data):
    return math.log(data["max_df"] / (1 + df))

# IDF method name -> function
IDF_METHODS = {"classic": idf_classic, "max": idf_max}

# TF weight with saturation and length normalization relative to the average document
def tf_weight(tf, length, data):
    norm = 1 - B + B * length / data["avg_length"]
    return tf * (K1 + 1) / (tf + K1 * norm)

# Rank documents for a query, return top_k (doc_id, score)
# Score = sum over query terms of tf_weight * idf, boosted by query terms in the title
def search(query, data, idf_method, top_k=10):
    idf = IDF_METHODS[idf_method]
    terms = tokenize(query)
    scores = {}
    for term in terms:
        postings = data["index"].get(term)
        if not postings:
            continue
        weight = idf(len(postings), data)
        for doc_id, tf in postings.items():
            length = data["doc_lengths"][doc_id]
            scores[doc_id] = scores.get(doc_id, 0) + tf_weight(tf, length, data) * weight

    # Title boost: documents with query terms in the title rank higher
    for doc_id in scores:
        title_terms = set(tokenize(data["docs"][doc_id]["title"]))
        matched = sum(1 for term in terms if term in title_terms)
        scores[doc_id] *= 1 + matched / len(terms)

    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    return ranked[:top_k]

# Top results of both IDF methods side by side
def compare(query, data, top_k=5):
    classic = search(query, data, "classic", top_k)
    max_idf = search(query, data, "max", top_k)
    print(f"===Compare: {query}===")
    print(f"   {'classic':<50} max")
    for rank in range(top_k):
        left = data["docs"][classic[rank][0]]["title"] if rank < len(classic) else ""
        right = data["docs"][max_idf[rank][0]]["title"] if rank < len(max_idf) else ""
        print(f"{rank + 1:>2}. {left[:48]:<50} {right[:48]}")

# Window of words around the rarest query term found in the text
def snippet(text, terms, data):
    words = text.split()
    present = [term for term in terms if term in data["index"]]
    for term in sorted(present, key=lambda term: len(data["index"][term])):
        for i, word in enumerate(words):
            if term in tokenize(word):
                start = max(0, i - SNIPPET_WORDS // 2)
                end = min(len(words), start + SNIPPET_WORDS)
                prefix = "..." if start > 0 else ""
                suffix = "..." if end < len(words) else ""
                return prefix + " ".join(words[start:end]) + suffix
    return None

# Key fields on one line, empty fields are skipped
def format_fields(fields):
    return " . ".join(f"{name}: {value}" for name, value in fields.items() if value is not None)

# Print ranked results with score, type, title, key fields and snippet
def print_results(query, data, idf_method, top_k=10):
    print(f"===Query: {query} (IDF {idf_method})===")
    results = search(query, data, idf_method, top_k)
    if not results:
        print("No results found.")
        return
    terms = tokenize(query)
    for rank, (doc_id, score) in enumerate(results, start=1):
        doc = data["docs"][doc_id]
        print(f"{rank:>2}. {score:7.3f} [{doc['type']}] {doc['title']}")
        fields = format_fields(doc["fields"])
        if fields:
            print(f"{'':12}{fields}")
        text = snippet(doc["text"], terms, data)
        if text:
            print(f"{'':12}{text}")
        print()

# Run one query with one IDF method or both
def run_query(query, data, idf_method):
    if idf_method == "compare":
        compare(query, data)
    else:
        print_results(query, data, idf_method)

# Read queries in a loop, lines starting with ":" are commands
def interactive(data, idf_method="classic"):
    print("F1 search. Type a query, :classic / :max / :compare to change IDF method, or :q to quit.")
    while True:
        try:
            line = input(f"f1 [{idf_method}]> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            continue
        if line in (":q", ":quit"):
            break
        if line.startswith(":"):
            if line[1:] in ("classic", "max", "compare"):
                idf_method = line[1:]
            else:
                print(f"Unknown IDF method: {line[1:]}")
            continue
        run_query(line, data, idf_method)
