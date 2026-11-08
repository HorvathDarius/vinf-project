import re

# === DUMP RECORD ===

# One record = text up to </page>, fields of the page from the dump XML
TITLE_RE = re.compile(r'<title>(.*?)</title>')
NS_RE = re.compile(r'<ns>(\d+)</ns>')
REDIRECT_RE = re.compile(r'<redirect title="(.*?)"\s*/>')
TEXT_RE = re.compile(r'<text[^>]*>(.*?)</text>', re.DOTALL)
# The dump escapes <, >, &, " inside the XML, decoded once per page
XML_ENTITY_RE = re.compile(r'&(lt|gt|quot|amp|apos);')
XML_ENTITIES = { "lt": "<", "gt": ">", "quot": '"', "amp": "&", "apos": "'" }



# === TYPES ===

# Infobox name -> our document type, names counted on the whole dump (pages mentioning F1)
PAGE_TYPES = [
    ("race", re.compile(r'\{\{\s*(?:Infobox[ _]Grand[ _]Prix[ _]race[ _]report|Grand[ _]Prix[ _]race[ _]report[ _]infobox)\b', re.IGNORECASE)),
    ("driver", re.compile(r'\{\{\s*Infobox[ _](?:F1|racing|Champ[ _]Car|Le[ _]Mans|NASCAR)[ _]driver\b', re.IGNORECASE)),
    ("track", re.compile(r'\{\{\s*Infobox[ _]motorsport[ _]venue\b', re.IGNORECASE)),
    # Teams: many constructors (BRM, Alfa Romeo, Ferrari) use the F1 engine manufacturer infobox
    ("team", re.compile(r'\{\{\s*Infobox[ _](?:F1[ _]team|former[ _]F1[ _]team|F1[ _]constructor|F1[ _]engine[ _]manufacturer|motor[ _]racing[ _]team)\b', re.IGNORECASE)),
]
# The page must mention F1
F1_MENTION_RE = re.compile(r'Formula One|Formula 1|Indianapolis 500')



# === WIKITEXT ===

# Infobox starts at the first {{Infobox, ends where the article text starts (bold title or first heading)
INFOBOX_START_RE = re.compile(r'\{\{\s*(?:Infobox|[^{}|\n]*[ _]infobox\b)', re.IGNORECASE)
INFOBOX_END_RE = re.compile(r"\n'''|\n==")
# One infobox field per line: | name = value
FIELD_RE = re.compile(r'^\s*\|\s*([A-Za-z0-9_ ]+?)\s*=[ \t]*(.*?)\s*$', re.MULTILINE)
FIRST_HEADING_RE = re.compile(r'\n==')

# Markup removed when cleaning wikitext into plain text
COMMENT_RE = re.compile(r'<!--.*?-->', re.DOTALL)
REF_RE = re.compile(r'<ref[^>]*/>|<ref[^>]*>.*?</ref>', re.DOTALL | re.IGNORECASE)
TEMPLATE_RE = re.compile(r'\{\{[^{}]*\}\}')  # innermost template, removed repeatedly
# Templates that carry text, replaced by it before removing the rest
TEXT_TEMPLATES = [
    (re.compile(r'\{\{\s*F1\s*\|\s*(\d{4})\s*\}\}', re.IGNORECASE), r'\1'),  # {{F1|1991}}
    (re.compile(r'\{\{\s*F1 ?GP\s*\|\s*([^{}|]*?)\s*\|\s*([^{}|]*?)\s*\}\}', re.IGNORECASE), r'\1 \2 Grand Prix'),  # {{F1GP|1991|Belgian}}
    (re.compile(r'\{\{\s*convert\s*\|\s*([^{}|]*?)\s*\|\s*([^{}|]*?)\s*(?:\|[^{}]*)?\}\}', re.IGNORECASE), r'\1 \2'),  # {{convert|23|C}}
    (re.compile(r'\{\{\s*(?:nowrap|nobr|small)\s*\|([^{}]*)\}\}', re.IGNORECASE), r'\1'),  # {{nowrap|x}}
    (re.compile(r'\{\{\s*lang\s*\|(?:[^{}|]*\|)*([^{}|=]*)\}\}', re.IGNORECASE), r'\1'),  # {{lang|de|italic=no|x}}
]
TABLE_RE = re.compile(r'\{\|.*?\n\|\}', re.DOTALL)
FILE_LINK_RE = re.compile(r'\[\[(?:File|Image|Category):(?:[^\[\]]|\[\[[^\[\]]*\]\])*\]\]', re.IGNORECASE)
LINK_RE = re.compile(r'\[\[(?:[^|\[\]]*\|)?([^\[\]]*)\]\]')
EXTERNAL_LINK_RE = re.compile(r'\[https?://[^\s\]]+\s*([^\]]*)\]')
BR_RE = re.compile(r'<br\s*/?>', re.IGNORECASE)
TAGS_RE = re.compile(r'<[^>]+>')
BOLD_ITALIC_RE = re.compile(r"'{2,}")
HEADING_RE = re.compile(r'^=+\s*(.*?)\s*=+\s*$', re.MULTILINE)
LIST_MARK_RE = re.compile(r'^[*#:;]+\s*', re.MULTILINE)
WHITESPACE_RE = re.compile(r'\s+')
# Leftovers of removed pronunciations: "( ; born" -> "(born", "( )" -> ""
EMPTY_PARENS_RE = re.compile(r'\(\s*[;,]?\s*\)')
PAREN_SEPARATOR_RE = re.compile(r'\(\s*[;,]\s*')
SPACE_BEFORE_PUNCT_RE = re.compile(r'\s+([,.;:)])')
# HTML entities left in the wikitext (&nbsp;, &ndash;, &#39;)
ENTITY_RE = re.compile(r'&(#[xX][0-9a-fA-F]+|#\d+|[a-zA-Z]+);')
NAMED_ENTITIES = {
    "nbsp": " ", "thinsp": " ", "hairsp": " ", "ensp": " ", "emsp": " ",
    "ndash": "–", "mdash": "—", "minus": "−", "times": "×", "middot": "·",
    "amp": "&", "lt": "<", "gt": ">", "quot": '"', "apos": "'", "shy": "", "zwj": "", "zwnj": "",
}

# Links and categories of the article
LINK_TARGET_RE = re.compile(r'\[\[(?!(?:File|Image|Category):)([^\[\]|#]+)', re.IGNORECASE)
CATEGORY_RE = re.compile(r'\[\[Category:([^\[\]|]+)', re.IGNORECASE)



# === INFOBOX VALUES ===

# {{birth date and age|1969|1|3|df=y}}, {{death date and age|...}}, {{start dat
DATE_TEMPLATE_RE = re.compile(r'\{\{\s*(?:birth|death|start|end)[ _]date[^|{}]*\|([^{}]*)\}\}', re.IGNORECASE)
NUMBER_PARAM_RE = re.compile(r'(?:^|\|)\s*(\d+)\s*(?=\||$)')
# Plain dates: "3 January 1969", "January 3, 1969", "12 March" (year from another field)
DAY_MONTH_YEAR_RE = re.compile(r'\b(\d{1,2})\s+([A-Z][a-z]+)\s*,?\s*(\d{4})?')
MONTH_DAY_YEAR_RE = re.compile(r'\b([A-Z][a-z]+)\s+(\d{1,2}),?\s*(\d{4})?')
MONTHS = {
    "January": 1, "February": 2, "March": 3, "April": 4, "May": 5, "June": 6, "July": 7,
    "August": 8, "September": 9, "October": 10, "November": 11, "December": 12,
}
# {{coord|52|23|20|N|4|32|27|E|type:landmark}} or {{coord|52.38|4.54}}
COORD_RE = re.compile(r'\{\{\s*coord\s*\|([^{}]*)\}\}', re.IGNORECASE)
COORD_PARAM_SPLIT_RE = re.compile(r'\s*\|\s*')
HEMISPHERES = {"N": 1, "S": -1, "E": 1, "W": -1}
FIRST_NUMBER_RE = re.compile(r'^\s*(\d+(?:[.,]\d+)*)')
YEAR_RE = re.compile(r'\b(1[89]\d\d|20\d\d)\b')



# === HELPER FUNCTION ===

# Decode the XML escaping of the dump
def decode_xml(text):
    return XML_ENTITY_RE.sub(lambda match: XML_ENTITIES[match.group(1)], text)

# Decode one HTML entity, unknown names stay as they are
def decode_entity(match):
    name = match.group(1)
    try:
        if name[:2] in ("#x", "#X"):
            return chr(int(name[2:], 16))
        if name[0] == "#":
            return chr(int(name[1:]))
    except (ValueError, OverflowError):
        return match.group(0)
    return NAMED_ENTITIES.get(name, match.group(0))

def decode_entities(text):
    return ENTITY_RE.sub(decode_entity, text)

# Remove templates from the intermost out, until nothing changes, text templates keep their text
def strip_templates(text):
    previous = None
    while previous != text:
        previous = text
        for template_re, replacement in TEXT_TEMPLATES:
            text = template_re.sub(replacement, text)
        text = TEMPLATE_RE.sub(" ", text)
    return text

# Title as a link target: first letter uppercase, underscore as space
def normalize_title(title):
    title = WHITESPACE_RE.sub(" ", title.replace("_", " ")).strip()
    return title[:1].upper() + title[1:]

# Year, month, day -> YYYY-MM-DD
def iso_date(year, month, day):
    return "{:04d}-{:02d}-{:02d}".format(int(year), int(month), int(day))



# === PAGE ===

# Title, namespace, redirect target and wikitext of one <page> record, None if it is not a page
def parse_page(record):
    title = TITLE_RE.search(record)
    if title is None:
        return None
    ns = NS_RE.search(record)
    redirect = REDIRECT_RE.search(record)
    text = TEXT_RE.search(record)
    return {
        "title": decode_xml(title.group(1)),
        "ns": int(ns.group(1)) if ns else None,
        "redirect": normalize_title(decode_xml(redirect.group(1))) if redirect else None,
        "text": decode_xml(text.group(1)) if text else ""
    }

# Our document type by the infobox names on the page, None if it is not an F1 page
def page_type(text):
    if "nfobox" not in text: # quick check before regexes
        return None
    if not F1_MENTION_RE.search(text):
        return None
    for doc_type, infobox_re in PAGE_TYPES:
        if infobox_re.search(text):
            return doc_type
    return None



# === WIKITEXT ===

# Wikitext -> plain text: no comments, refs, templates, tables, files, link markup, tags, entities
def clean_wikitext(text):
    if not text:
        return ""
    text = COMMENT_RE.sub(" ", text)
    text = REF_RE.sub(" ", text)
    text = strip_templates(text)
    text = TABLE_RE.sub(" ", text)
    text = FILE_LINK_RE.sub(" ", text)
    text = LINK_RE.sub(r"\1", text)
    text = EXTERNAL_LINK_RE.sub(r"\1", text)
    text = BR_RE.sub(", ", text)
    text = TAGS_RE.sub(" ", text)
    text = BOLD_ITALIC_RE.sub("", text)
    text = HEADING_RE.sub(r"\1", text)
    text = LIST_MARK_RE.sub(" ", text)
    text = decode_entities(text)
    text = WHITESPACE_RE.sub(" ", text)
    text = EMPTY_PARENS_RE.sub("", text)
    text = PAREN_SEPARATOR_RE.sub("(", text)
    text = SPACE_BEFORE_PUNCT_RE.sub(r"\1", text)
    return WHITESPACE_RE.sub(" ", text).strip(" ,")

# Text of the article before the first heading
def abstract(text):
    heading = FIRST_HEADING_RE.search(text)
    return clean_wikitext(text[:heading.start()] if heading else text)

# Article text without markup
def article_text(text):
    return clean_wikitext(text)

# Linked article titles, without duplicate
def links(text):
    seen = []
    for target in LINK_TARGET_RE.findall(text):
        title = normalize_title(target)
        if title and title not in seen:
            seen.append(title)
    return seen

def categories(text):
    return [normalize_title(name) for name in CATEGORY_RE.findall(text)]



# === INFOBOX ===

# Part of the wikitext with the infobox (and the infoboxes embedded in it)
def infobox_block(text):
    start = INFOBOX_START_RE.search(text)
    if start is None:
        return ""
    end = INFOBOX_END_RE.search(text, start.end())
    return text[start.start():end.start() if end else len(text)]

# Raw infobox fields, lowercase names, first value wins (embedded F1 infobox before Le Mans etc.)
def infobox_fields(text):
    fields = {}
    for name, value in FIELD_RE.findall(infobox_block(text)):
        key = WHITESPACE_RE.sub("_", name.strip().lower())
        if value and key not in fields:
            fields[key] = value
    return fields

# Infobox value as plain text, None if empty
def clean_value(value):
    text = clean_wikitext(value)
    return text or None

# First number of a value: "7 (1994, 1995, ...)" -> 7, "105,000" -> 105000, "4.259" -> 4.259
def first_number(value):
    match = FIRST_NUMBER_RE.search(clean_wikitext(value)) if value else None
    if match is None:
        return None
    number = match.group(1).replace(",", "")
    return float(number) if "." in number else int(number)

# Date from a date template or a plain date, year from another field if missing
def parse_date(value, year=None):
    if not value:
        return None
    template = DATE_TEMPLATE_RE.search(value)
    if template:
        numbers = NUMBER_PARAM_RE.findall(template.group(1))
        return iso_date(*numbers[:3]) if len(numbers) >= 3 else None
    text = clean_wikitext(value)
    match = DAY_MONTH_YEAR_RE.search(text)
    if match and match.group(2) in MONTHS:
        day, month, found_year = match.group(1), MONTHS[match.group(2)], match.group(3)
    else:
        match = MONTH_DAY_YEAR_RE.search(text)
        if match is None or match.group(1) not in MONTHS:
            return None
        day, month, found_year = match.group(2), MONTHS[match.group(1)], match.group(3)
    found_year = found_year or year
    return iso_date(found_year, month, day) if found_year else None

# Year from a date template or the first year in the value: "1927", "{{Start date|1948|08|07}}"
def parse_year(value):
    date = parse_date(value)
    if date:
        return int(date[:4])
    match = YEAR_RE.search(clean_wikitext(value)) if value else None
    return int(match.group(1)) if match else None

# Degrees, minutes, seconds -> decimal degrees
def dms(parts):
    return sum(float(part) / (60 ** i) for i, part in enumerate(parts))

# Latitude and longitude from {{coord}}, None if missing
def coordinates(value):
    match = COORD_RE.search(value or "")
    if match is None:
        return None
    params = [param for param in COORD_PARAM_SPLIT_RE.split(match.group(1).strip()) if "=" not in param]
    hemispheres = [i for i, param in enumerate(params) if param in HEMISPHERES]
    try:
        if len(hemispheres) >= 2:
            lat_end, lon_end = hemispheres[0], hemispheres[1]
            lat = dms(params[:lat_end]) * HEMISPHERES[params[lat_end]]
            lon = dms(params[lat_end + 1:lon_end]) * HEMISPHERES[params[lon_end]]
        else:
            lat, lon = float(params[0]), float(params[1])
    except (ValueError, IndexError):
        return None
    return [round(lat, 4), round(lon, 4)]



# === ENTITIES ===

# Fields of each type: output name -> (infobox field names, parser)
ENTITY_FIELDS = {
    "driver": {
        "birth_date": (["birth_date"], parse_date),
        "death_date": (["death_date"], parse_date),
        "birth_place": (["birth_place"], clean_value),
        "nationality": (["nationality"], clean_value),
        "teams": (["teams"], clean_value),
        "races": (["races"], first_number),
        "championships": (["championships"], first_number),
        "wins": (["wins"], first_number),
        "podiums": (["podiums"], first_number),
        "poles": (["poles"], first_number),
        "first_race": (["first_race"], clean_value),
        "last_race": (["last_race"], clean_value),
    },
    "race": {
        "year": (["year"], first_number),
        "official_name": (["official_name"], clean_value),
        "location": (["location"], clean_value),
        "course_km": (["course_km"], first_number),
        "laps": (["distance_laps"], first_number),
        "distance_km": (["distance_km"], first_number),
        "weather": (["weather"], clean_value),
        "attendance": (["attendance"], first_number),
        "pole_driver": (["pole_driver"], clean_value),
        "pole_time": (["pole_time"], clean_value),
        "fastest_driver": (["fast_driver"], clean_value),
        "fastest_time": (["fast_time"], clean_value),
        "winner": (["first_driver"], clean_value),
        "winner_team": (["first_team"], clean_value),
        "second_driver": (["second_driver"], clean_value),
        "third_driver": (["third_driver"], clean_value),
    },
     "track": {
        "location": (["location"], clean_value),
        "coordinates": (["coordinates", "coord"], coordinates),
        "opened": (["opened"], parse_year),
        "capacity": (["capacity"], first_number),
        "length_km": (["length_km"], first_number),
        "turns": (["turns"], first_number),
        "record_time": (["record_time"], clean_value),
        "record_driver": (["record_driver"], clean_value),
        "record_year": (["record_year"], first_number),
    },
    "team": {
        "full_name": (["long_name", "full_name", "constructor_name"], clean_value),
        "base": (["base"], clean_value),
        "founders": (["founders", "founder"], clean_value),
        "principal": (["principal", "team_principal"], clean_value),
        "debut": (["debut", "first_entry"], clean_value),
        "races": (["races"], first_number),
        "constructors_titles": (["cons_champ", "constructors_championships"], first_number),
        "drivers_titles": (["drivers_champ", "drivers_championships"], first_number),
        "wins": (["wins"], first_number),
    },
}

# First infobox field that exists, parsed
def entity_field(fields, names, parser):
    for name in names:
        if name in fields:
            return parser(fields[name])
    return None

# Wiki entity of one F1 page: title, type, infobox attributes, abstract, text, links, categories
def wiki_entity(page, doc_type):
    text = page["text"]
    fields = infobox_fields(text)
    entity = {"title": page["title"], "type": doc_type}
    for name, (field_names, parser) in ENTITY_FIELDS[doc_type].items():
        entity[name] = entity_field(fields, field_names, parser)
    if doc_type == "race":  # race date is "12 March", the year is a separate field
        entity["date"] = parse_date(fields.get("date") or fields.get("fulldate"), entity["year"])
    entity["abstract"] = abstract(text)
    entity["text"] = article_text(text)
    entity["categories"] = categories(text)
    entity["links"] = links(text)
    return entity