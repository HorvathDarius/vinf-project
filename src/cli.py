import argparse
import traceback

import crawling.crawl as crawl
import crawling.crawl_fansite as crawl_fansite
import extraction.extract as extract
import basic_search.index as index
import basic_search.search as search
import stats

# Search engines: own index from part 1, Lucene index from part 2, or both side by side
ENGINES = ["old", "lucene", "compare"]
# Results per engine in the side by side comparison
COMPARE_TOP_K = 5

# Crawl one source or both
def run_crawl(source):
    if source in ("driverdb", "all"):
        crawl.crawl_driverdb()
    if source in ("f1-fansite", "all"):
        crawl_fansite.crawl_f1_fansite()

# Handlers for the subcommands, args come from argparse
def cmd_crawl(args):
    run_crawl(args.source)

def cmd_extract(args):
    extract.extract_all()

def cmd_index(args):
    if args.engine == "lucene":
        build_lucene_index()
    else:
        index.build()

# Search one query, or start interactive search if no query is given
def cmd_search(args):
    query_text = " ".join(args.query)
    if args.engine == "lucene":
        search_lucene(query_text)
    elif args.engine == "compare":
        compare_engines(query_text)
    else:
        data = search.load_index()
        if query_text:
            search.run_query(query_text, data, args.idf)
        else:
            search.interactive(data, args.idf)

def cmd_stats(args):
    stats.print_stats()

# Parse command line arguments, without a command open the menu
def main():
    parser = argparse.ArgumentParser(prog="cli.py", description="F1 search engine (VINF Project)")
    commands = parser.add_subparsers(dest="command")

    crawl_parser = commands.add_parser("crawl", help="Crawl data from sources (driverdb.com and f1-fansite.com)")
    crawl_parser.add_argument("source", choices=["driverdb", "f1-fansite", "all"], help="Source to crawl")
    crawl_parser.set_defaults(func=cmd_crawl)

    extract_parser = commands.add_parser("extract", help="Extract data from crawled HTML files into .jsonl files")
    extract_parser.set_defaults(func=cmd_extract)

    index_parser = commands.add_parser("index", help="Build inverted index from extracted .jsonl files")
    index_parser.add_argument("--engine", choices=["old", "lucene"], default="old", help="Own index (part 1) or Lucene index (part 2)")
    index_parser.set_defaults(func=cmd_index)

    search_parser = commands.add_parser("search", help="Search the index for a query")
    search_parser.add_argument("query", nargs="*", help="Query string to search for")
    search_parser.add_argument("--idf", choices=["classic", "max", "compare"], default="classic", help="IDF method to use for scoring")
    search_parser.add_argument("--engine", choices=ENGINES, default="old", help="Own index (part 1), Lucene index (part 2), or both side by side")
    search_parser.set_defaults(func=cmd_search)

    stats_parser = commands.add_parser("stats", help="Print statistics about the data")
    stats_parser.set_defaults(func=cmd_stats)

    args = parser.parse_args()
    if args.command is None:
        menu()
    else:
        args.func(args)

# Read one line, Ctrl+C / Ctrl+D count as exit
def ask(prompt):
    try:
        return input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return "0"

# Crawl submenu, asks for confirmation because a full crawl takes hours
def menu_crawl():
    sources = {"1": "driverdb", "2": "f1-fansite", "3": "all"}
    print("1. driverdb.com\n2. f1-fansite.com\n3. both\n0. back")
    choice = ask("crawl> ")
    if choice not in sources:
        return
    answer = ask("Crawling takes hours, already downloaded pages are skipped. Continue? [y/N] ")
    if answer.lower() == "y":
        run_crawl(sources[choice])

# Interactive search with the default IDF method
def menu_search():
    search.interactive(search.load_index())



# === LUCENE ===
# Lucene is imported only when used: on the Mac (uv) PyLucene is not installed, the old search still works there

# Start the Java VM once per process (a second initVM fails) and return the Lucene modules
def lucene_modules():
    try:
        import lucene
    except ImportError:
        raise RuntimeError("PyLucene is not installed here, run the CLI with ./run_lucene.sh src/cli.py")
    if lucene.getVMEnv() is None:
        lucene.initVM()
    from lucene_search import lucene_build, lucene_query
    return lucene_build, lucene_query

# Same steps as lucene_build.main(), without starting the VM again
def build_lucene_index():
    lucene_build, lucene_query = lucene_modules()
    docs = lucene_build.load_documents()
    lucene_build.print_documents_stats(docs)
    lucene_build.build_index(docs)
    lucene_build.print_index_stats()

# One query, or interactive search without one
def search_lucene(query_text=None):
    lucene_build, lucene_query = lucene_modules()
    lucene_searcher = lucene_query.LuceneSearcher()
    if query_text:
        lucene_query.print_results(lucene_searcher, query_text)
    else:
        lucene_query.interactive(lucene_searcher)
    lucene_searcher.close()

# Top results of the old index (classic IDF) and the Lucene index side by side
def compare_query(query_text, data, lucene_searcher):
    import lucene
    old_results = search.search(query_text, data, "classic", COMPARE_TOP_K)
    try:
        query = lucene_searcher.parse(query_text)
    except lucene.JavaError as error:
        print("Invalid query: {}".format(error.getJavaException().getMessage()))
        return
    total, new_results = lucene_searcher.search(query, COMPARE_TOP_K)
    print("===Compare: {}===".format(query_text))
    print("   {:<50} {}".format("old index", "lucene ({} hits)".format(total)))
    for rank in range(COMPARE_TOP_K):
        left = data["docs"][old_results[rank][0]]["title"] if rank < len(old_results) else ""
        right = new_results[rank][1].get("title") if rank < len(new_results) else ""
        print("{:>2}. {:<50} {}".format(rank + 1, left[:48], right[:60]))
    print()

# Compare one query, or read queries in a loop until :q
def compare_engines(query_text=None):
    lucene_build, lucene_query = lucene_modules()
    data = search.load_index()
    lucene_searcher = lucene_query.LuceneSearcher()
    if query_text:
        compare_query(query_text, data, lucene_searcher)
    else:
        print("Old index vs Lucene index. Type a query, or :q to quit.")
        while True:
            line = ask("f1 [compare]> ")
            if line in ("0", ":q", ":quit"):
                break
            if line:
                compare_query(line, data, lucene_searcher)
    lucene_searcher.close()




# Menu option -> (label, function)
MENU = {
    "1": ("Crawl", menu_crawl),
    "2": ("Extract", extract.extract_all),
    "3": ("Index", index.build),
    "4": ("Search", menu_search),
    "5": ("Stats", stats.print_stats),
     "6": ("Lucene index", build_lucene_index),
    "7": ("Lucene search", search_lucene),
    "8": ("Compare old vs Lucene", compare_engines),
}

# Main menu loop, an error in one action is printed and the menu continues
def menu():
    while True:
        print("\n===== F1 search engine 1950-2026 =====")
        for key, (label, action) in MENU.items():
            print(f"{key}. {label}")
        print("0. Exit")
        choice = ask("> ")
        if choice == "0":
            break
        if choice not in MENU:
            print("Unknown option.")
            continue
        label, action = MENU[choice]
        try:
            action()
        except KeyboardInterrupt:
            print(f"\n{label} interrupted.")
        except Exception:
            traceback.print_exc()

if __name__ == "__main__":
    main()