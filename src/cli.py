import argparse
import traceback

import crawl
import crawl_fansite
import extract
import index
import search
import stats

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
    index.build()

# Search one query, or start interactive search if no query is given
def cmd_search(args):
    data = search.load_index()
    if args.query:
        search.run_query(" ".join(args.query), data, args.idf)
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
    index_parser.set_defaults(func=cmd_index)

    search_parser = commands.add_parser("search", help="Search the index for a query")
    search_parser.add_argument("query", nargs="*", help="Query string to search for")
    search_parser.add_argument("--idf", choices=["classic", "max", "compare"], default="classic", help="IDF method to use for scoring")
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

# Menu option -> (label, function)
MENU = {
    "1": ("Crawl", menu_crawl),
    "2": ("Extract", extract.extract_all),
    "3": ("Index", index.build),
    "4": ("Search", menu_search),
    "5": ("Stats", stats.print_stats),
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