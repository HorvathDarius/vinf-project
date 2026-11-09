# 3. Konzultácia – Spracovanie veľkých dát (Spark, Wikipédia)

Kód: https://github.com/HorvathDarius/vinf-project, branch `main`, adresár `src/` (`spark_extract.py`, `spark_wiki.py`, `wiki.py`, `spark_join.py`) a `run_spark.sh`.

Celé spracovanie sú tri Spark joby, každý číta iba výstup predchádzajúceho:

```
krok 1  data/<typ>/*.html (3 403 stránok, 966 MB)  ──► spark_extract.py ──► extracted_spark/<typ>.jsonl
krok 2  wiki_dump/*.bz2 (71 súborov, 24 GB)         ──► spark_wiki.py    ──► wiki_spark/entities.jsonl, redirects.jsonl
krok 3  extracted_spark/*.jsonl + wiki_spark/*      ──► spark_join.py    ──► extracted_spark/wiki_<typ>.jsonl
```

## Rozšírenie kódu z prvého odovzdania na Spark

### Prostredie

Spark beží v Docker image z prednášky `iisas/hadoop-spark-pig-hive:2.9.2` (Spark 2.4.3, Hadoop 2.9.2, Java 8, Python 3.6.9). Image je iba pre `amd64`, na Macu s Apple Silicon beží v emulácii. Joby spúšťa skript `run_spark.sh`:

```bash
docker run --rm --platform linux/amd64 \
  -v "$PWD":/project -w /project \
  -e PYSPARK_PYTHON=python3 \
  -e PYTHONPATH=/project/src \
  -e LANG=C.UTF-8 -e PYTHONIOENCODING=utf-8 \
  --entrypoint bash \
  iisas/hadoop-spark-pig-hive:2.9.2 \
  -c 'export SPARK_DIST_CLASSPATH=$(hadoop classpath); spark-submit --master "local[*]" --driver-memory 10g "$@"' _ "$@"
```

```bash
./run_spark.sh src/spark_extract.py
./run_spark.sh src/spark_wiki.py
./run_spark.sh src/spark_join.py
```

Projekt je do kontajnera pripojený (`-v`), takže úprava kódu nevyžaduje rebuild a výstupy pristanú na disku hostiteľa. Čo bolo treba nastaviť a prečo:

- `PYSPARK_PYTHON=python3`: predvolený `python` v image je 2.7, workery by bežali v ňom.
- `SPARK_DIST_CLASSPATH`: Spark v image je zostavený bez Hadoopu, bez tejto premennej padne pri štarte na chýbajúcich triedach Hadoopu (potrebujeme ich aj na čítanie bz2).
- `LANG`, `PYTHONIOENCODING`: Python 3.6 bez locale zapisuje ASCII, prvé meno s diakritikou (Räikkönen) by spadlo.
- `--entrypoint bash`: pôvodný entrypoint image štartuje celý Hadoop klaster (HDFS, YARN), ktorý lokálne nepotrebujeme.
- `--driver-memory 10g`: v lokálnom režime je driver aj executor jeden proces, takže je to celý heap Sparku. Docker má pridelených 16 GB, zvyšok je pre Python workery a OS.

Kód z prvej časti bol písaný pre Python 3.14, v image je 3.6. Upraviť bolo treba jediný riadok (`extract.py:245`, f-string s vnorenými úvodzovkami, ktoré Python 3.6 nepozná). Nový kód je písaný tak, aby bežal v oboch verziách (`.format()`, žiadne `:=`).

### Parser z prvej časti ako Spark job (`src/spark_extract.py`)

Regex extraktory z prvej časti (`extract_driver`, `extract_race_result`, …) sú nezmenené a importované z `extract.py`. Spark nahrádza iba cyklus, ktorý ich volal postupne pre každú stránku. Driver vytvorí z crawl logov zoznam úloh `(typ, kľúč, cesta, URL)`, workery čítajú HTML z disku a extrahujú:

```python
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
```

```python
pages = spark.sparkContext.parallelize(tasks, PARTITIONS).map(extract_task).cache()
pages.count()
```

`cache()` drží výsledky, aby sa pri zápise piatich súborov (jeden na typ, cez `filter`) nespúšťala extrakcia päťkrát.

Overenie: výstup v `extracted_spark/` je **bajt po bajte zhodný** s výstupom prvej časti v `extracted/` (`cmp`, 5 z 5 súborov). Beh: 3 403 stránok, 966 MB HTML, extrakcia 9 s, spolu 16 s na 12 jadrách.

## Extrakcia a spracovanie dát (vrátane wiki dumpu) pomocou Sparku

### Dump

`enwiki-20261001-pages-articles` z [dumps.wikimedia.org](https://dumps.wikimedia.org/enwiki/20261001/) (aktuálna verzia každej stránky, bez histórie a diskusií): 71 súborov bz2, spolu 25,8 GB. Rozdelený dump namiesto jedného veľkého súboru, lebo každý súbor je prirodzená jednotka práce pre Spark a sťahovanie sa dá obnoviť po súboroch. Integrita overená proti `enwiki-20261001-md5sums.txt`, 71/71 súborov sedí. Súbory sú vo `wiki_dump/`, git ich nevidí.

### Čítanie dumpu (`src/spark_wiki.py`)

Dump sa číta cez Hadoop `TextInputFormat` s vlastným oddeľovačom záznamov `</page>`, takže jeden záznam je jedna stránka. Hadoop zároveň rozbaľuje bz2:

```python
# One record = one <page>...</page>, one input split = one whole bz2 file (no splitting of compressed files)
HADOOP_CONF = {
    "textinputformat.record.delimiter": "</page>",
    "mapreduce.input.fileinputformat.split.minsize": str(10 ** 12),
}
```

```python
records = sc.newAPIHadoopFile(
    dump_path,
    "org.apache.hadoop.mapreduce.lib.input.TextInputFormat",
    "org.apache.hadoop.io.LongWritable",
    "org.apache.hadoop.io.Text",
    conf=HADOOP_CONF,
).map(lambda pair: pair[1])
pages = records.flatMap(count_and_process).persist(StorageLevel.MEMORY_AND_DISK)
```

`split.minsize = 10^12`: jeden súbor je jeden task, paralelizmus je po súboroch (71 súborov na 12 jadrách). `persist` drží spracované záznamy, aby sa 24 GB dump čítal iba raz, hoci z neho robíme dva výstupy (entity a redirecty). Počet prečítaných stránok počíta `accumulator`.

Pri 25,9 mil. stránok rozhoduje poradie kontrol. Najprv lacné testy podreťazca, až potom regexy, väčšina stránok sa zahodí bez jediného regexu:

```python
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
```

Z 12 mil. redirectov ponechávame iba tie, ktoré smerujú na naše entity. Množina titulov entít sa pošle workerom raz cez `broadcast` a redirecty sa filtrujú `target in titles`. Slúžia ako tabuľka aliasov pre join.

Výstup sú dva JSONL súbory: `entities.jsonl` (F1 stránky s extrahovanými poľami, 48,7 MB) a `redirects.jsonl` (title -> target, 0,3 MB). Join a všetko ďalšie beží nad nimi v sekundách, dump sa číta iba v tomto kroku.

### Štatistika plného behu

| | počet |
|---|---|
| stránky v dumpe (`<page>`) | 25 932 290 |
| redirecty v mennom priestore článkov | 12 065 403 |
| z toho smerujúce na naše entity | 4 719 |
| F1 entity spolu | 4 492 |
| – jazdci | 2 475 |
| – preteky | 1 586 |
| – okruhy | 212 |
| – tímy | 219 |
| čas behu (12 jadier, emulácia amd64) | 16 min 11 s |

## Práca s wiki dátami pomocou regexov

Všetko parsovanie je v `src/wiki.py`, iba modul `re`, bez XML parsera a bez knižníc na wikitext. Stránka pretekov má vo wikitexte infobox, napr. 2006 Bahrain Grand Prix (skrátené):

```
{{Infobox Grand Prix race report
|Type          = F1
|Date          = 12 March
|Year          = 2006
|Official name = 2006 Formula 1 Gulf Air Bahrain Grand Prix
|Location      = [[Bahrain International Circuit]]<br>[[Sakhir]], [[Bahrain]]
|Course_km     = 5.412
|Distance_laps = 57
| Weather = Fine, Dry and Hot<br>Air Temp {{convert|23|C}}<ref name=weather>{{cite news|...}}</ref>
|Attendance    = 77,000 (Weekend)<ref>{{Cite web|...}}</ref>
|Pole_Driver   = [[Michael Schumacher]]
|First_driver  = [[Fernando Alonso]]
...
}}
The '''2006 Bahrain Grand Prix''' (officially the ...) was a [[Formula One]] motor race ...
```

### Polia stránky z XML

```python
TITLE_RE = re.compile(r'<title>(.*?)</title>')
NS_RE = re.compile(r'<ns>(\d+)</ns>')
REDIRECT_RE = re.compile(r'<redirect title="(.*?)"\s*/>')
TEXT_RE = re.compile(r'<text[^>]*>(.*?)</text>', re.DOTALL)
```

Dump má v texte escapované `&lt;`, `&gt;`, `&amp;`, `&quot;`, dekódujú sa raz na stránku regexom `&(lt|gt|quot|amp|apos);`.

### Relevancia: ktorá stránka je F1 a akého typu

Stránka je naša, ak spomína „Formula One“, „Formula 1“ alebo „Indianapolis 500“ a obsahuje jeden z infoboxov:

```python
PAGE_TYPES = [
    ("race", re.compile(r'\{\{\s*(?:Infobox[ _]Grand[ _]Prix[ _]race[ _]report|Grand[ _]Prix[ _]race[ _]report[ _]infobox)\b', re.IGNORECASE)),
    ("driver", re.compile(r'\{\{\s*Infobox[ _](?:F1|racing|Champ[ _]Car|Le[ _]Mans|NASCAR)[ _]driver\b', re.IGNORECASE)),
    ("track", re.compile(r'\{\{\s*Infobox[ _]motorsport[ _]venue\b', re.IGNORECASE)),
    ("team", re.compile(r'\{\{\s*Infobox[ _](?:F1[ _]team|former[ _]F1[ _]team|F1[ _]constructor|F1[ _]engine[ _]manufacturer|motor[ _]racing[ _]team)\b', re.IGNORECASE)),
]
F1_MENTION_RE = re.compile(r'Formula One|Formula 1|Indianapolis 500')
```

| náš typ | infobox | stránok v dumpe |
| --- | --- | --- |
| preteky | `Infobox Grand Prix race report` (aj `Grand Prix race report infobox`) | 1 560 |
| jazdec | `F1 driver`, `racing driver`, `Champ Car driver`, `Le Mans driver`, `NASCAR driver` | 857 / 1 389 / 194 / 321 / 86 |
| okruh | `motorsport venue` | 193 |
| tím | `F1 team`, `former F1 team`, `F1 constructor`, `F1 engine manufacturer`, `motor racing team` | 26 / 22 / 19 / 45 / 115 |

`[ _]` lebo Wikipédia v názve šablóny nerozlišuje medzeru a podčiarkovník, `IGNORECASE` lebo nerozlišuje ani veľkosť písmen. Jazdci Indianapolis 500 z rokov 1950 – 1960 (súčasť MS, napr. Bill Vukovich) nemajú infobox F1, preto aj iné série a zmienka „Indianapolis 500“. Jazdci F1 majú infobox často vnorený, `| module = {{Infobox F1 driver` vo vnútri `{{Infobox person`, preto sa typ hľadá v celom texte, nie iba v prvom infoboxe.

### Polia infoboxu

```python
INFOBOX_START_RE = re.compile(r'\{\{\s*(?:Infobox|[^{}|\n]*[ _]infobox\b)', re.IGNORECASE)
INFOBOX_END_RE = re.compile(r"\n'''|\n==")
FIELD_RE = re.compile(r'^\s*\|\s*([A-Za-z0-9_ ]+?)\s*=[ \t]*(.*?)\s*$', re.MULTILINE)
```

Infobox začína prvým `{{Infobox` (alebo `{{… infobox`) a končí tam, kde začína text článku (tučný názov `'''` alebo prvý nadpis `==`). Koniec sa nehľadá párovaním zátvoriek `}}`, lebo hodnoty obsahujú vnorené šablóny a regex zátvorky nespáruje. Vnorené infoboxy (F1 driver v Infobox person) sú tak v jednom bloku. `FIELD_RE` berie jeden riadok `| názov = hodnota`: `^` s `MULTILINE` kotví na začiatok riadku, `\s*\|\s*` je rúra s ľubovoľnými medzerami, skupina 1 je názov, skupina 2 celá hodnota po koniec riadku. Názvy sa prevedú na malé písmená a medzery na `_` (`Official name` -> `official_name`), platí prvá hodnota (pole z F1 infoboxu má prednosť pred Le Mans).

Hodnota sa necháva celá, aj s `<ref>` a šablónami, a čistí sa až parserom podľa typu poľa. Čo vráti na riadkoch z ukážky:

| riadok infoboxu | parser | výsledok |
|---|---|---|
| `\|Date = 12 March` + `\|Year = 2006` | `parse_date` s rokom z poľa `Year` | `2006-03-12` |
| `\|Location = [[Bahrain International Circuit]]<br>[[Sakhir]], [[Bahrain]]` | `clean_value` | `Bahrain International Circuit, Sakhir, Bahrain` |
| `\| Weather = Fine, Dry and Hot<br>Air Temp {{convert\|23\|C}}<ref>…` | `clean_value` | `Fine, Dry and Hot, Air Temp 23 C, Track Temp 40 C dropping to 34 C` |
| `\|Attendance = 77,000 (Weekend)<ref>…</ref>` | `first_number` | `77000` |
| `\|Course_km = 5.412` | `first_number` | `5.412` |
| `\|Pole_Driver = [[Michael Schumacher]]` | `clean_value` | `Michael Schumacher` |

Parsery hodnôt, všetko regexy:

- `parse_date`: šablóny `{{birth date and age|1969|1|3}}`, `{{start date|…}}` (prvé tri čísla), aj text „3 January 1969“, „January 3, 1969“, „12 March“ (rok z iného poľa).
- `first_number`: „7 (1994, 1995, …)“ -> 7, „105,000“ -> 105000, „4.259“ -> 4.259.
- `coordinates`: `{{coord|52|23|20|N|4|32|27|E}}` (stupne, minúty, sekundy + pologuľa) aj `{{coord|52.38|4.54}}` -> `[52.3889, 4.5408]`.

### Čistenie wikitextu

`clean_wikitext` (pre hodnoty, `abstract` = text pred prvým nadpisom a `text` = celý článok) odstraňuje značky v tomto poradí:

1. komentáre `<!-- -->`, referencie `<ref>…</ref>` a `<ref … />`
2. šablóny `{{…}}` od najvnútornejšej, opakovane, kým sa text mení. Regex `\{\{[^{}]*\}\}` chytí iba šablónu bez vnorených, po jej odstránení sa vonkajšia stane najvnútornejšou. Šablóny, ktoré nesú text, sa nahradia textom: `{{F1|1991}}` -> `1991`, `{{F1GP|1991|Belgian}}` -> `1991 Belgian Grand Prix`, `{{convert|23|C}}` -> `23 C`, `{{nowrap|…}}`, `{{lang|de|…}}`
3. tabuľky `{| … |}`, obrázky a kategórie `[[File:…]]`, `[[Category:…]]`
4. odkazy `[[cieľ|text]]` -> `text`, `[[cieľ]]` -> `cieľ`, externé odkazy, `<br>` -> `, `, HTML tagy, `'''tučné'''`, nadpisy, odrážky
5. HTML entity (`&nbsp;`, `&ndash;`, `&#39;`) vlastným regex dekodérom, zvyšky zátvoriek po výslovnosti (`( ; born` -> `(born`)

```python
# Remove templates from the innermost out, until nothing changes, text templates keep their text
def strip_templates(text):
    previous = None
    while previous != text:
        previous = text
        for template_re, replacement in TEXT_TEMPLATES:
            text = template_re.sub(replacement, text)
        text = TEMPLATE_RE.sub(" ", text)
    return text
```

## Join: logika a zdôvodnenie (`src/spark_join.py`)

Mená sa v zdrojoch píšu rôzne: driverdb.com „Grand Prix of Bahrain“, f1-fansite.com „Azerbaijan F1 Grand Prix“, Wikipédia „2006 Bahrain Grand Prix“; okruh „Autodromo Nazionale Monza“ je na Wikipédii „Monza Circuit“. Join preto nie je iba podľa titulu. Pre každý typ je kľúč, ktorý majú obe strany spoločný, a druhý atribút na overenie:

| typ | kľúč joinu | overenie (`verified`) |
| --- | --- | --- |
| jazdec | normalizované meno (titul + redirecty) | dátum narodenia |
| výsledky / report pretekov | dátum pretekov (+- 1 deň), záložne „rok podujatie“ | víťaz |
| okruh | meno, slug, redirecty; súradnice < 5 km | vzdialenosť < 5 km |
| tím | meno, celé meno, slug, redirecty | – (iba meno) |

Normalizované meno = `tokenize` z prvej časti (malé písmená, bez diakritiky, bez stop slov) bez zátvoriek: „Nelson Piquet (racing driver)“ -> `nelson piquet`, „Kimi Räikkönen“ -> `kimi raikkonen`. +- 1 deň, lebo f1-fansite.com datuje časť reportov dňom po pretekoch (2025 Azerbaijan GP: report 22. 9., preteky 21. 9.). Kľúče sú dvojice `(typ, hodnota)`, takže jazdec sa nikdy nespojí s okruhom rovnakého mena.

Prečo join: obe strany sú množiny záznamov s rovnakým kľúčom, Spark ich spojí v jednom kroku. Cyklus „pre každý dokument hľadaj v entitách“ by bol 3 403 × 4 492 porovnaní. Join má štyri kroky:

```python
# Wiki key table: (key type, key) -> title, from titles, race dates and redirects (aliases)
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
```

1. **Tabuľka wiki kľúčov**: titul každej entity, dátum pretekov a aliasy. `redirects x entities` na titule cieľa, takže každý redirect sa stane ďalším kľúčom svojej entity s jej typom.
2. **Kandidáti**: `our_keys x wiki_keys` na `(typ, kľúč)`. Jeden dokument môže mať viac kandidátov (napr. tri dátumy +- 1 deň).
3. **Okruhy podľa súradníc**: `cartesian` našich okruhov so všetkými wiki okruhmi (87 × 212 dvojíc, malé), ponechané dvojice bližšie než 5 km (haversine). Zachytí okruhy, ktorých mená sa nezhodujú vôbec.
4. **Výber**: `leftOuterJoin` dokumentov s kandidátmi (každý dokument ostane, bez kandidáta dostane `None`), `best_match` vyberie najlepšieho kandidáta podľa metódy `verified` > `name` > `date`. Posunutý dátum bez rovnakého víťaza sa zamietne. Entity sa workerom pošlú raz cez `broadcast`.

Join na pretekoch, len stĺpce, ktoré použije. Náš dokument z driverdb.com sa s titulom nezhoduje (`2006 grand prix bahrain` vs. `2006 bahrain grand prix`), spojí sa cez dátum:

| náš dokument: id | name | date | winner | kľúče |
|---|---|---|---|---|
| race:2006-round-1 | Grand Prix of Bahrain | 2006-03-12 | Fernando Alonso | `race_date 2006-03-11`, `race_date 2006-03-12`, `race_date 2006-03-13`, `race 2006 grand prix bahrain` |

| wiki kľúče: kľúč | title |
|---|---|
| `race_date 2006-03-12` | 2006 Bahrain Grand Prix |
| `race 2006 bahrain grand prix` | 2006 Bahrain Grand Prix |
| `race_date 2006-03-19` | 2006 Malaysian Grand Prix |

Krok 2: zhodne sa iba `race_date 2006-03-12`, kandidát je „2006 Bahrain Grand Prix“. 
Krok 4: `best_match` porovná víťaza, `fernando alonso` = `fernando alonso`, metóda `verified`:

| výsledok: id | wiki_title | match | wiki.date | wiki.pole_driver | wiki.attendance |
|---|---|---|---|---|---|
| race:2006-round-1 | 2006 Bahrain Grand Prix | verified | 2006-03-12 | Michael Schumacher | 77000 |

## Koľko unikátnych wiki stránok sme pripojili

| typ | dokumentov | prepojených | % | unikátnych wiki stránok | verified | name | date |
| --- | --- | --- | --- | --- | --- | --- | --- |
| jazdci | 902 | 884 | 98,0 % | 881 | 858 | 26 | – |
| výsledky pretekov | 1 020 | 1 014 | 99,4 % | 1 014 | 980 | – | 34 |
| reporty pretekov | 1 166 | 1 160 | 99,5 % | 1 160 | 1 141 | – | 19 |
| okruhy | 87 | 64 | 73,6 % | 58 | 49 | 15 | – |
| tímy | 228 | 36 | 15,8 % | 35 | – | 36 | – |
| **spolu** | **3 403** | **3 158** | **92,8 %** | **2 136** | | | |

**Pripojili sme 2 136 unikátnych wiki stránok**: 881 jazdcov, 1 162 pretekov, 58 okruhov a 35 tímov. Súčet riadkov je vyšší, lebo výsledky a report tých istých pretekov zdieľajú jednu wiki stránku. Join beží 21 s.

Nespárované:

- **tímy (192)**: väčšina „tímov“ v DriverDB sú súkromní prihlasovatelia z 50. a 60. rokov (Écurie Rosier, Horschell Racing Corporation) alebo jazdci prihlasujúci sa sami (Achille Varzi, Bob Estes), ktorí vlastnú stránku nemajú (Ecurie Belge je iba redirect na jazdca Johnny Claes). Konštruktéri so stránkou používajú aj všeobecný `Infobox company` (Lotus Cars, Ligier, Sauber), ktorý by do výberu pridal stovky výrobcov áut a sponzorov.
- **okruhy (23)**: iný názov bez redirectu (Estoril, Bremgarten, Albert Park ako „Melbourne Grand Prix Circuit“).

## Aké atribúty z wiki sú pre nás zaujímavé

Ukážka prepojeného záznamu (`extracted_spark/wiki_drivers.jsonl`, skrátené):

```json
{
  "id": "driver:kimi-raikkonen",
  "type": "driver",
  "wiki_title": "Kimi Räikkönen",
  "match": "verified",
  "wiki": {
    "birth_date": "1979-10-17",
    "birth_place": "Espoo, Uusimaa, Finland",
    "nationality": "Finnish",
    "teams": "Sauber, McLaren, Ferrari, Lotus, Alfa Romeo",
    "races": 353,
    "championships": 1,
    "wins": 21,
    "podiums": 103,
    "poles": 18,
    "first_race": "2001 Australian Grand Prix",
    "last_race": "2021 Abu Dhabi Grand Prix",
    "abstract": "Kimi-Matias Räikkönen (born 17 October 1979) is a Finnish racing and rally driver who competed in Formula One between 2001 and 2021, …",
    "categories": ["1979 births", "Living people", "Alfa Romeo Formula One drivers", "…"],
    "links": ["2019 Austrian Grand Prix", "Espoo", "Formula One drivers from Finland", "…"]
  }
}
```

| typ | atribút | prečo |
| --- | --- | --- |
| všetky | `abstract`, `text` | súvislý text (životopis, história, opis pretekov), DriverDB má iba čísla a tabuľky; fulltext v Lucene |
| všetky | `categories` | „Finnish racing drivers“, „Formula One World Drivers' Champions“: dopyty typu „finnish world champions“ |
| všetky | redirecty (aliasy) | alternatívne mená („Kimi Raikkonen“, „Johnny Dumfries“), vyhľadanie bez diakritiky a pod iným menom |
| všetky | `links` | prepojenia jazdec – tím – preteky, signál významnosti pre ranking |
| jazdec | `championships`, `wins`, `podiums`, `poles` | kariérna štatistika, číselné polia pre rozsahové dopyty (`wins:[20 TO *]`) |
| jazdec | `teams`, `first_race`, `last_race`, `birth_place`, `death_date` | za koho jazdil, kariéra, miesto narodenia |
| preteky | `pole_driver`, `pole_time`, `fastest_driver`, `fastest_time` | pole position a najrýchlejšie kolo, naše výsledky ich nemajú |
| preteky | `weather`, `attendance`, `official_name` | počasie aj pri pretekoch bez reportu, návštevnosť, oficiálny názov so sponzorom |
| okruh | `length_km`, `turns`, `record_time`, `record_driver` | dĺžka, zákruty, rekord okruhu (Monza: 5,793 km, 11 zákrut, 1:20.901 Lando Norris 2025) |
| okruh | `opened`, `capacity`, `coordinates` | rok otvorenia, kapacita, poloha |
| tím | `base`, `founders`, `principal`, `constructors_titles`, `drivers_titles` | sídlo, zakladateľ, šéf tímu, tituly (Ferrari: Maranello, Enzo Ferrari, 16 + 15) |

### Čo je iba na Wikipédii

Údaje, ktoré nemá ani driverdb.com, ani f1-fansite.com:

| typ | iba na Wikipédii |
| --- | --- |
| jazdec | životopis (`abstract`, `text`), tímy kariéry (`teams`), prvé a posledné preteky, kategórie |
| preteky | pole position a čas, najrýchlejšie kolo a čas, návštevnosť, oficiálny názov so sponzorom, dĺžka okruhu v danom roku, úvod o pretekoch |
| okruh | rok otvorenia, kapacita, počet zákrut, rekord okruhu (čas, jazdec, rok) |
| tím | zakladateľ, debut, počet konštruktérskych a jazdeckých titulov, história tímu |
| všetky | alternatívne mená z redirectov, kategórie, odkazy na súvisiace články |

Wikipédia teda nedopĺňa iba text na fulltextové vyhľadávanie, ale aj nové štruktúrované polia (napr. pole position alebo rekord okruhu), na ktoré sa z pôvodných dát nedalo pýtať vôbec.
