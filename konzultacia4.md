# 4. Konzultácia – Lucene index

Kód: https://github.com/HorvathDarius/vinf-project, branch `main`. Nové súbory: `src/lucene_search/lucene_build.py` (stavba indexu), `src/lucene_search/lucene_query.py` (vyhľadávanie), úpravy v `src/cli.py`, prostredie `Dockerfile.lucene` a `run_lucene.sh`.

```
extracted_spark/<typ>.jsonl + extracted_spark/wiki_<typ>.jsonl ──► lucene_build.py ──► index/lucene/
index/lucene/ + dopyt                                          ──► lucene_query.py ──► výsledky (cli.py --engine lucene)
```

## Hotový Spark kód

Tri Spark joby z 3. konzultácie (`src/spark/spark_extract.py`, `spark_wiki.py`, `spark_join.py`) sú hotové. Od minulej konzultácie sa zmenilo:

- **Novší Docker image.** Image z prednášky `iisas/hadoop-spark-pig-hive:2.9.2` má na Docker Hube jediný tag z roku 2020 (Spark 2.4.3, Python 3.6, iba `amd64`). Prešli sme na oficiálny `apache/spark:4.3.0-python3` (Spark 4.3.0, Hadoop 3.5, Java 21, Python 3.10, natívne aj pre `arm64`). Kód jobov sa nemenil, používa iba RDD API. Všetkých 12 výstupných súborov (extrakcia, wiki, join) je po prechode bajtovo zhodných s výstupmi starého image.
- **Oprava opakovaného spustenia joinu.** Join číta `extracted_spark/*.jsonl` a do toho istého priečinka zapisuje `wiki_<typ>.jsonl`. Pri druhom behu načítal aj vlastný výstup (6 561 namiesto 3 403 dokumentov) a padol na `KeyError`. Filter teraz preskakuje záznamy s kľúčom `wiki_title`.
- **Priečinky v `src/`:** `crawling/`, `extraction/`, `spark/`, `basic_search/` (index z 1. časti), `lucene_search/` (index z 2. časti).

## Prostredie PyLucene

PyLucene nie je balík na PyPI: je to Java knižnica Lucene obalená generátorom JCC a musí sa skompilovať proti JDK. Používame preto hotový image `coady/pylucene:10.0.0` (Lucene 10.0.0, Python 3.15), doplnený o závislosti projektu:

```dockerfile
FROM coady/pylucene:10.0.0
RUN pip install --no-cache-dir requests tiktoken
```

`run_lucene.sh` funguje rovnako ako `run_spark.sh`: zostaví image, pripojí projekt do kontajnera a spustí `python` so zadaným skriptom. Celé CLI (aj crawl, extrakcia a starý index) beží v tomto image:

```bash
./run_lucene.sh src/cli.py index --engine lucene
./run_lucene.sh src/cli.py search --engine lucene 'type:driver AND wins:[30 TO *]'
```

## Návrh a implementácia indexu (`src/lucene_search/lucene_build.py`)

### Vstup: jeden Lucene dokument na jeden náš dokument

Index sa stavia z výstupu Sparku. Pre každý typ sa načítajú naše dokumenty a k nim podľa `id` pripojené wiki dáta z joinu:

| typ | dokumentov | s wiki dátami |
| --- | ---: | ---: |
| jazdec | 902 | 884 |
| výsledky pretekov | 1 020 | 1 014 |
| reporty pretekov | 1 166 | 1 160 |
| okruh | 87 | 64 |
| tím | 228 | 36 |
| **spolu** | **3 403** | **3 158** |

Dokument bez zhody zostáva v indexe, iba nemá wiki polia.

### Analyzer

Analyzer určuje, ako sa text rozloží na termy, pri indexovaní aj pri dopyte. Zopakuje kroky funkcie `tokenize()` zo starého indexu, vrátane rovnakého zoznamu stop slov:

```python
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
```

`ASCIIFoldingFilter` mení „Räikkönen“ na „raikkonen“, takže meno sa nájde s diakritikou aj bez nej, rovnako ako v starom indexe.

### Typy polí

| Lucene typ | pomocná funkcia | čo robí | na čo |
| --- | --- | --- | --- |
| `TextField` | `add_text` | text rozložený analyzerom na termy, s pozíciami | slová, frázy, fuzzy |
| `StringField` | `add_keyword` | celá hodnota ako jeden term (malými písmenami) | presný filter (`nationality:finnish`) |
| `IntField` | `add_int` | číslo uložené v strome (points) | rozsahové dopyty (`wins:[30 TO *]`) |

Pole je *stored*, ak sa jeho pôvodná hodnota zobrazuje vo výsledkoch. Prázdne hodnoty sa nepridávajú, chýbajúci údaj teda nevytvorí pole.

### Skóre

Vyhľadávanie používa BM25 s parametrami `k1 = 1.2`, `b = 0.75`, rovnakými ako náš BM25 z 1. časti. Rozdiely vo výsledkoch teda pochádzajú z indexu (polia, wiki dáta, typy dopytov), nie zo vzorca.

## Odôvodnenie polí

Polia sme vyberali podľa týchto pravidiel:

1. **Samostatné pole iba vtedy, keď umožní dopyt, ktorý `text` nevie.** Pole `text` obsahuje všetky naše údaje (miesto narodenia, ocenenia, celé výsledky), takže sú vyhľadateľné aj bez vlastného poľa. Vlastné pole má zmysel iba pre presný filter (`StringField`), číselný rozsah (`IntField`) alebo hľadanie v konkrétnej úlohe (`winner:senna` namiesto akejkoľvek zmienky).
2. **Naše dáta majú prednosť, Wikipédia dopĺňa chýbajúce.** Údaje, ktoré máme úplné (dátumy, národnosť, `f1_stats`, víťaz), berieme z našich dát. Z Wikipédie iba to, čo naše zdroje nemajú: tímy jazdca, pole position, tím víťaza, počet kôl, parametre okruhu a text článku.
3. **Pokrytie.** Pole pridávame, iba ak ho má väčšina dokumentov daného typu (`laps` 999 / 1 014, `pole_driver` 1 003 / 1 014). Vynechali sme `attendance` (379 / 1 014), `capacity` okruhov (39 / 64), `founders` a `principal` tímov (20 a 13 / 36). Výnimkou sú `wins` a `constructors_titles` tímov (22 a 31 z 228 tímov): pridali sme ich, lebo inak by tímy nemali žiadne číselné pole, obmedzenie je uvedené nižšie.
4. **Hodnota musí zodpovedať typu poľa.** Časy kôl (`pole_time`, `fastest_time`, `record_time`) by bolo treba prevádzať a žiadny náš dopyt ich nepoužíva. Súradnice nevyužijeme bez geografických dopytov a `links` sú iba zoznam odkazov (šum).
5. **Bez duplicít.** `second_driver` a `third_driver` sú už v našich výsledkoch (v `text`), `course_km` a `distance_km` nahrádza `laps` a `length_m` okruhu.

### Spoločné polia (všetky dokumenty, `add_common_fields`)

| pole | typ | stored | zdroj | prečo |
| --- | --- | :---: | --- | --- |
| `id` | `StringField` | áno | naše | jednoznačný kľúč dokumentu |
| `type` | `StringField` | áno | naše | filter na typ (`type:driver`), zúženie dopytu, keď viac typov zdieľa pole |
| `title` | `TextField` | áno | naše | meno jazdca, názov pretekov; pri dopyte boost ×3 (nahrádza title boost z 1. časti) |
| `text` | `TextField` | áno | naše | rovnaký text ako v starom indexe; zdroj snippetu |
| `wiki_title` | `TextField` | áno | wiki | druhý variant mena („Andy Linden (racing driver)“); boost ×2 |
| `wiki_abstract` | `TextField` | áno | wiki | prvý odsek článku; náhradný snippet, keď `text` dopyt neobsahuje |
| `wiki_text` | `TextField` | nie | wiki | celý článok: fakty, ktoré naše zdroje nemajú (kde a ako jazdec zahynul); nie je stored, lebo je veľký a iba sa prehľadáva; boost ×0,5, aby dlhý text neprebil meno |
| `wiki_categories` | `TextField` | nie | wiki | „Formula One World Drivers' Champions“, „Formula One constructors“: dopyty na zaradenie entity |

Dopyt bez mena poľa sa hľadá v týchto šiestich textových poliach naraz, s uvedenými boostmi.

### Jazdec (`add_driver_fields`)

| pole | typ | zdroj | prečo |
| --- | --- | --- | --- |
| `nationality` | `StringField` | naše | presný filter (`nationality:finnish`), bez čiastočných zhôd |
| `birth_year` | `IntField` | naše `birth_date` | rozsah: jazdci narodení v rokoch 1960 – 1969 |
| `races`, `wins`, `podiums`, `poles` | `IntField` | naše `f1_stats` | rozsah: `wins:[30 TO *]` |
| `titles` | `IntField` | naše, počet `f1_titles` | `titles:[1 TO *]` = majstri sveta |
| `title_year` | `IntField`, viac hodnôt | naše `f1_titles` | `title_year:[1990 TO 1999]` = majstri 90. rokov |
| `teams` | `TextField` | wiki | „jazdci, ktorí jazdili za Ferrari“ |

Čísla berieme z našich dát, nie z Wikipédie: `f1_stats` má všetkých 902 jazdcov ako celé čísla, kým na Wikipédii 42 – 55 jazdcov tieto hodnoty nemá a pri 506 jazdcoch sa počet pretekov líši (pravdepodobne prihlásenia vs. štarty).

### Preteky – výsledky aj reporty (`add_race_fields`)

| pole | typ | zdroj | prečo |
| --- | --- | --- | --- |
| `year` | `IntField` | naše | rozsah: `year:[1980 TO 1989]` |
| `date` | `IntField` (`19510527`) | naše | rozsah podľa dátumu; prevod regexom `^(\d{4})-(\d{2})-(\d{2})$` |
| `winner`, `track` | `TextField`, stored | naše | fráza: `winner:"ayrton senna"` |
| `pole_driver`, `winner_team` | `TextField` | wiki | „preteky, kde Senna štartoval z pole position“; naše výsledky ich nemajú |
| `laps` | `IntField` | wiki | rozsah počtu kôl |

### Okruh a tím (`add_track_fields`, `add_team_fields`)

| pole | typ | zdroj | prečo |
| --- | --- | --- | --- |
| `country` | `StringField` | naše | filter na krajinu; okruhy majú kódy (`au`), tímy názvy (`great britain`) |
| `length_m` | `IntField` | wiki `length_km` × 1000 | rozsah dĺžky okruhu (celé číslo, preto metre) |
| `turns`, `opened` | `IntField` | wiki | rozsah počtu zákrut, roku otvorenia |
| `wins`, `constructors_titles` | `IntField` | wiki (iba tímy) | rozsah; obmedzenie: hodnoty má iba 36 tímov so zhodou |

Rovnaké meno poľa vo viacerých typoch (`wins` jazdca aj tímu, `country` okruhu aj tímu) znamená, že jeden dopyt pokryje viac typov a `type:` ho zúži.

### Index na disku

| | starý index | Lucene index |
| --- | --- | --- |
| formát | `index/index.json` | `index/lucene/` (segmenty Lucene) |
| veľkosť | 28 MB | 14 MB, aj s celým wiki textom a číselnými poľami |
| načítanie | celý súbor do pamäte pri každom štarte | z disku sa číta iba to, čo dopyt potrebuje |
| vstup | 19 MB (naše dáta) | naše dáta + 39 MB wiki dát z joinu |
| stavba (načítanie + indexovanie + zápis) | 0,8 s | 2,0 s |

## Implementácia nového indexu do aplikácie

`lucene_query.py` otvorí index raz a pri každom dopyte: parsuje text dopytu, vyhľadá s BM25 a vypíše poradie, skóre, typ, názov, kľúčové polia a snippet so zvýraznenými termami. Dopyt parsuje `StandardQueryParser`, ktorý má nastavené:

- **predvolené polia s boostmi** pre slová bez mena poľa,
- **číselné polia** (`PointsConfig`), bez ktorých by `wins:[30 TO *]` porovnával text a nenašiel nič,
- **keyword analyzer** pre `StringField` polia, takže `country:"Great Britain"` sa zhoduje s uloženou hodnotou `great britain`.

V `cli.py` pribudla voľba `--engine`:

```bash
./run_lucene.sh src/cli.py index  --engine lucene                     # postaví Lucene index
./run_lucene.sh src/cli.py search --engine lucene  'winner:senna'     # vyhľadá v Lucene indexe
./run_lucene.sh src/cli.py search --engine compare  ayrton senna      # starý a nový index vedľa seba
./run_lucene.sh src/cli.py search                   ayrton senna      # starý index, ako v 1. časti
```

Predvolený je `--engine old`, takže pôvodné príkazy fungujú bez zmeny. V menu pribudli položky 6 (Lucene index), 7 (Lucene search) a 8 (porovnanie). Lucene sa importuje až pri použití: na Macu cez `uv` PyLucene nie je a starý index tam funguje ďalej. Java VM sa štartuje raz za proces (druhé `initVM()` zlyhá), takže v menu sa dá postaviť index, vyhľadávať aj porovnávať v jednej relácii.

## Typy dopytov

Všetky príklady sú z nášho indexu.

| typ | dopyt | výsledok |
| --- | --- | --- |
| **Boolean AND** | `type:driver AND nationality:finnish AND titles:[1 TO *]` | 3: Rosberg, Räikkönen, Häkkinen |
| **Boolean OR** | `ayrton senna` (predvolený operátor) | 567 zásahov, 1. Ayrton Senna, 2. Bruno Senna |
| **Boolean NOT** | `schumacher NOT michael`, `senna -type:race_report -type:race_result` | 118 zásahov bez slova „michael“; Senna bez pretekov (1. Ayrton Senna) |
| **Range** | `type:driver AND wins:[30 TO *]` | 7: Prost, Senna, Alonso, Verstappen, Schumacher, Hamilton, Vettel |
| **Range, viac hodnôt** | `type:driver AND title_year:[1990 TO 1999]` | 7 majstrov 90. rokov |
| **Range z wiki** | `type:track AND length_m:[6000 TO *]` | Baku, Spa, Jeddah, Pescara, Reims |
| **Phrase** | `winner:"ayrton senna"` | iba preteky, ktoré vyhral Senna |
| **Phrase + Range** | `"san marino" AND year:[1994 TO 1994]` | 1. 1994 San Marino Grand Prix |
| **Fuzzy** | `raikonen~` | 1. Kimi Räikkönen (preklep, max. 2 zmeny) |
| **Pole + Boolean** | `winner:senna AND track:monaco` | 9: šesť reportov (1987, 1989 – 1993) a tri výsledky (1991 – 1993) |
| **Wiki text + filter** | `type:driver AND killed AND imola` | Paletti, Bellof, Senna, de Angelis, Ratzenberger |

Starý index z 1. časti vedel iba slová spojené OR: bez operátorov AND/OR/NOT, bez fráz, rozsahov, fuzzy a polí.

## Porovnanie dopytov: starý vs. nový index

Výsledky z `search --engine compare` (top 5). Starý index: BM25 s klasickým IDF a title boostom, iba naše dáta. Nový index: Lucene, BM25, naše dáta + Wikipédia.

### Rovnaké slová, oba indexy

**`ayrton senna monaco`**

| # | starý index | Lucene |
| ---: | --- | --- |
| 1 | 1993 Monaco Grand Prix | **Ayrton Senna** |
| 2 | 1991 Monaco Grand Prix | Bruno Senna |
| 3 | 1992 Monaco Grand Prix | 1993 Monaco Grand Prix |
| 4 | 1984 Monaco F1 Grand Prix Race Report | 1992 Monaco Grand Prix |
| 5 | 1989 Monaco F1 Grand Prix Race Report | 1991 Monaco Grand Prix |

Lucene dá na prvé miesto samotného jazdca: zhoda v `title` má boost ×3 a jeho wiki článok spomína Monako 18-krát. Starý index preferuje krátke dokumenty výsledkov, v ktorých sú všetky tri slová.

**`ferrari constructor`**

| # | starý index | Lucene |
| ---: | --- | --- |
| 1 | 1962 British F1 Grand Prix Race Report | **Ferrari** |
| 2 | 1964 Dutch F1 Grand Prix Race Report | Autodromo Enzo e Dino Ferrari |
| 3 | 1964 French F1 Grand Prix Race Report | 1967 Belgian F1 Grand Prix Race Report |
| 4 | 1966 French F1 Grand Prix Race Report | 1962 French F1 Grand Prix Race Report |
| 5 | 1966 Monaco F1 Grand Prix Race Report | 1957 British F1 Grand Prix Race Report |

Obe slová sú aj v našom texte tímu Ferrari, starý index však uprednostní reporty, v ktorých sa „Ferrari“ opakuje mnohokrát. V Lucene rozhoduje zhoda „Ferrari“ v poli `title` s boostom ×3. Wiki kategórie tu nepomáhajú: obsahujú iba tvar „constructors“ a index nepoužíva stemming, takže sa so slovom „constructor“ nezhodujú.

**`schumacher`**

| # | starý index | Lucene |
| ---: | --- | --- |
| 1 | Ralf Schumacher | **Michael Schumacher** |
| 2 | Mick Schumacher | Mick Schumacher |
| 3 | Michael Schumacher | Ralf Schumacher |
| 4 | 1998 Luxembourg F1 Grand Prix Race Report | 2002 San Marino F1 Grand Prix Race Report |
| 5 | 1998 Argentine F1 Grand Prix Race Report | 2002 Malaysian F1 Grand Prix Race Report |

V starom indexe vyhráva najkratší profil (normalizácia dĺžky BM25). V Lucene rozhoduje `wiki_text`: Michaelov článok obsahuje „Schumacher“ 364-krát, Ralfov 148-krát a Mickov 85-krát.

**`finnish world champion`**: oba indexy majú na prvých troch miestach Häkkinena, Räikkönena a Rosberga. Ak je odpoveď priamo v našich dátach, indexy sa zhodujú.

**`driver killed in crash`**

| # | starý index | Lucene |
| ---: | --- | --- |
| 1 | 2000 Spanish F1 Grand Prix Race Report | Paddy Driver |
| 2 | 1977 South African F1 Grand Prix Race Report | Peter Whitehead |
| 3 | Race Results 2015 Monaco F1 GP | Eddie Johnson |
| 4 | 1978 United States F1 Grand Prix Race Report | Ricardo Rodriguez |
| 5 | 1968 Belgian F1 Grand Prix Race Report | Van Johnson |

Slabina nového indexu: slová sú spojené OR a zhoda jedného slova v `title` (boost ×3) prebije dokumenty, ktoré obsahujú všetky slová v texte. „Driver“ je priezvisko jazdca Paddyho Drivera. Rovnaký jav je pri `lewis hamilton british champion`: po Hamiltonovi nasledujú Jackie Lewis a Duncan Hamilton. Riešením je presnejší dopyt, napr. `type:driver AND killed AND crash`.

### Dopyty, ktoré vie iba nový index

Starý index dostane rovnaký text, syntax však rozloží na obyčajné slová.

| dopyt | Lucene | starý index |
| --- | --- | --- |
| `type:driver AND wins:[30 TO *]` | 7 správnych jazdcov | náhodné preteky so slovom „30“ |
| `type:driver AND title_year:[1990 TO 1999]` | 7 majstrov 90. rokov | preteky z rokov 1990 a 1999 |
| `type:track AND length_m:[6000 TO *]` | Baku, Spa, Jeddah, Pescara, Reims | nesúvisiace preteky |
| `winner:senna AND track:monaco` | 9, presne Sennove víťazstvá v Monaku v našich dátach | preteky v Monaku bez ohľadu na víťaza |
| `schumacher NOT michael` | 118 zásahov, žiadny s „michael“ | „not“ a „michael“ sú hľadané slová |
| `raikonen~` | 1. Kimi Räikkönen | 0 výsledkov |
| `type:driver AND killed AND imola` | Paletti, Bellof, Senna, de Angelis, Ratzenberger | reporty z Veľkej ceny San Marína |

Posledný dopyt najlepšie ukazuje prínos joinu: štyria z prvých piatich jazdcov zahynuli po nehode, Senna a Ratzenberger v Imole 1994. Táto informácia je iba vo `wiki_text`.

### Zhrnutie

- **Nový index je lepší**, keď je odpoveď v štruktúrovaných poliach (rozsahy, filtre, frázy) alebo iba na Wikipédii (kategórie, životopis).
- **Pri obyčajných slovách** dávajú oba indexy podobné výsledky, ak je odpoveď priamo v našich dátach. Lucene častejšie dá na prvé miesto entitu (jazdca, tím) namiesto pretekov.
- **Slabina nového indexu:** OR medzi slovami spolu s boostom `title` vynáša dokumenty, ktoré sa zhodujú v jednom slove mena (Paddy Driver).
- **Obmedzenia dát, nie indexu:** preklep bez `~` nenájde žiadny z indexov; výsledky pretekov z rokov 1982 – 1990 v našich dátach chýbajú (reporty sú kompletné).

## Odkaz na GitHub

https://github.com/HorvathDarius/vinf-project
