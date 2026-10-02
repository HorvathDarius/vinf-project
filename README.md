# 1. Konzultácia – Výber a potvrdenie projektu + dáta

## Opis projektu

Vyhľadávač jazdcov Formuly 1 (1950 – 2026). Hlavným dokumentom je jazdec, ku ktorému prepájame jeho sezóny, tímy, výsledky pretekov a okruhy. Štruktúrované dáta crawlujeme z Driver Database (driverdb.com), textové reporty z pretekov z F1-Fansite (f1-fansite.com), regexom z nich extrahujeme atribúty a vzťahy a postavíme nad nimi vlastný index. Používateľ zadá voľný text (napr. „drivers who raced for ferrari and mclaren") a dostane zoradený zoznam jazdcov. V druhej časti záznamy spojíme s anglickou Wikipédiou (Spark nad dumpom) a index prebudujeme v PyLucene.

Motivácia: DriverDB sa dá prezerať len ako sezóna → výsledková listina, alebo jazdec po jazdcovi. Otázky naprieč entitami („za aké tímy jazdil Senna", „ktorí Taliani vyhrali v Monze") sa v nej položiť nedajú.

## Scrapované stránky

### driverdb.com

Renderované na serveri (HTTP request bez JavaScriptu vráti všetky hodnoty), bez bot ochrany, jednotná šablóna pre každý typ stránky. robots.txt povoľuje všetko okrem `/api/` a nepredpisuje `Crawl-delay`, medzi requestmi čakáme 2 s.

| Typ dokumentu | URL | Počet | Atribúty |
| --- | --- | --- | --- |
| **jazdec** (hlavný) | `/drivers/<slug>` | 885 | národnosť, dátum a miesto narodenia, tímy a sezóny, kariérne štatistiky |
| sezóna (5 záložiek) | `/championships/formula-1/<rok>/…` | 77 | majstri sveta, kalendár, výsledková listina |
| výsledky pretekov | `…/<rok>/results/round-<n>/race-1` | 1 013 | Veľká cena, okruh, víťaz, pole position, najrýchlejšie kolo, klasifikácia |
| okruh | `/tracks/<slug>` | 119 | názov, krajina, rok otvorenia, popisný text |
| tím | `/teams/<slug>` | 272 | názov, krajina, sezóny v F1, popisný text |

Príklady: <https://www.driverdb.com/drivers/lewis-hamilton> (GB, 7 Jan 1985, McLaren / Mercedes / Ferrari), <https://www.driverdb.com/championships/formula-1/2026/results/round-13/race-1> (Italian GP, Monza), <https://www.driverdb.com/tracks/monza>.

**Crawl.** Seed je `/championships/formula-1`. Zo `standings` každej sezóny berieme jazdcov a tímy, z `calendar` kolá `/results/round-<n>` (len prechádzame) a z nich preteky `race-1`, ktoré odkazujú na okruh. Navštívené URL preskakujeme, ignorujeme parametrizované URL, obrázky a odkazy na iné šampionáty. Next.js vracia status 200 aj pre neexistujúce stránky, preto stránku ukladáme len ak obsahuje očakávaný obsah.

**Obmedzenie.** Výsledky pretekov chýbajú pre sezónu 1981 (8 z 15 pretekov) a sezóny 1982 – 1990; standings pre tieto sezóny existujú, takže vzťah jazdec – tím – rok je úplný.

### f1-fansite.com

Súvislý text má DriverDB len pri tímoch a okruhoch, pri jazdcoch a pretekoch sú to čísla a tabuľky. Preto pridávame druhú doménu s reportmi z pretekov (priebeh, súboje, stratégia, nehody, výroky jazdcov) vrátane počasia a teploty trate. robots.txt zakazuje len `/wp-admin/`, parametrizované URL obchodu a vyhľadávanie; `/f1-result/` je povolené a `Crawl-delay` nie je predpísaný. Ide o WordPress so sémantickým HTML (`<strong>Weather:</strong>`, `<strong>Track:</strong>`), takže sa extrahuje rovnako regexom.

Príklad: <https://www.f1-fansite.com/f1-result/race-report-results-2026-italian-formula-1-grand-prix/> (~2 000 slov textu, ~323 kB). Reporty existujú pre všetky sezóny od 1950. Ukladáme len telo článku, navigáciu, bočný panel a diskusiu čitateľov odrezávame.

**Spojenie s DriverDB.** Kľúčom je dvojica (rok, okruh): v rámci sezóny zarovnáme kalendár z DriverDB (poradie kôl s okruhmi) so zoznamom reportov a správnosť overíme porovnaním víťaza z oboch zdrojov.

**Objem.** Spolu ~3 366 dokumentov a ~994 MB surového HTML: preteky 337 MB, reporty z f1-fansite ~330 MB, jazdci ~165 MB, sezóny 108 MB, okruhy ~32 MB, tímy ~22 MB. Veľkosti stránok sme zmerali, počty zistili prechodom všetkých sezón. Crawl má ~3 700 requestov, pri 2 s približne 2 hodiny; hranicu 500 MB prekračujeme už samotnými crawlovanými dátami, bez dumpu Wikipédie.

## Wikipedia

V druhej časti pripájame články z dumpu `enwiki-latest-pages-articles.xml.bz2` cez Spark. Hlavný je join jazdcov cez meno, overený dátumom narodenia v infoboxe (rieši menovcov).

| Driver Database | Wikipedia |
| --- | --- |
| `/drivers/lewis-hamilton` | <https://en.wikipedia.org/wiki/Lewis_Hamilton> |
| `/championships/formula-1/1976/standings` | <https://en.wikipedia.org/wiki/1976_Formula_One_World_Championship> |
| `/tracks/monza` | <https://en.wikipedia.org/wiki/Monza_Circuit> |
| `/teams/ferrari` | <https://en.wikipedia.org/wiki/Scuderia_Ferrari> |

Čo Wikipédia pridáva a ani jeden z našich zdrojov to nemá:

| Zdroj vo Wikipédii | Čo z toho máme |
| --- | --- |
| text článku | životopis jazdca, príčina úmrtia, rodinné väzby (Hill, Rosberg, Villeneuve, Verstappen) |
| infobox | tituly (`Championships`), dátum úmrtia (`death_date`), dĺžka okruhu a traťový rekord (`length_km`, `record_time`), sídlo a zakladateľ tímu (`Base`, `Founder`) |
| presmerovania | alternatívne zápisy mien (Räikkönen / Raikkonen, Hélio / Helio Castroneves) ako tabuľka aliasov pre join |
| odkazy a anchor texty | graf prepojení medzi jazdcami, tímami a pretekmi + signál významnosti pre ranking |
| tabuľky výsledkov | preteky sezón 1981 – 1990, ktoré DriverDB nemá |

## Príklady dopytov a odpovedí

Odpoveďou je zoznam jazdcov zoradený podľa relevancie, pri každom národnosť, tímy a relevantné výsledky.

| # | Dopyt | Očakávaná odpoveď | Čo testuje |
| --- | --- | --- | --- |
| 1 | Lewis Hamilton | Lewis Hamilton | presná zhoda mena |
| 2 | teams Ayrton Senna drove for | Toleman, Lotus, McLaren, Williams | jazdec → tímy |
| 3 | drivers who raced for ferrari and mclaren | Lauda, Prost, Räikkönen, Alonso | prienik dvoch tímov |
| 4 | finnish world champions | Rosberg, Häkkinen, Räikkönen | národnosť + umiestnenie |
| 5 | 2026 italian grand prix winner | Andrea Kimi Antonelli | preteky → jazdec |
| 6 | italian drivers who won at monza | Farina, Ascari, Scarfiotti | národnosť + okruh + výsledky |
| 7 | race won after a safety car restart | preteky s safety carom v reporte | voľný text z f1-fansite |
| 8 | drivers who died in a racing accident | Senna, Bianchi, Villeneuve | údaj z Wikipédie |
