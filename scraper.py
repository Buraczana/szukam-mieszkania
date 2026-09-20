#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Skaner ofert mieszkań na sprzedaż (rynek wtórny) w Warszawie.

WERSJA 5 - naprawia "zero wyników mimo istniejących ofert" (np. na ul.
Kasprowicza i Płatniczej). Dwie potwierdzone (nie domniemane) przyczyny,
zweryfikowane bezpośrednio na żywej stronie i na testach:

PRZYCZYNA A: błędny adres URL wyszukiwania Otodom.
  Skaner używał ".../mieszkanie/rynek-wtorny/mazowieckie/warszawa/warszawa/
  warszawa" - to nie jest poprawny format. Sprawdzony na żywo, działający
  adres to ".../mieszkanie,rynek-wtorny/mazowieckie/warszawa" (przecinek
  między "mieszkanie" i "rynek-wtorny", BEZ potrójnego powtórzenia
  "warszawa"). Przy błędnym adresie Otodom nie zwraca błędu HTTP - po cichu
  pokazuje 0 ogłoszeń dla nierozpoznanej lokalizacji, więc nic tego nie
  sygnalizowało w logach. Ten błąd był obecny już w poprzedniej wersji -
  wcześniej maskował go Tabelaofert.pl, który i tak zwracał (niedoskonałe)
  wyniki z innych źródeł; po jego usunięciu wyszło na jaw, że sam Otodom nic
  nie zwracał.

PRZYCZYNA B: mechanizm "stop przy drugiej cenie" (dodany, by nie mylić
  sąsiednich ogłoszeń) błędnie liczył cenę ZA METR ("19 714 zł/m2") jako
  sygnał drugiej, sąsiedniej karty - a każda, pojedyncza karta ogłoszenia
  pokazuje ZARÓWNO cenę całkowitą, JAK I cenę za metr (obie ze słowem "zł").
  W efekcie mechanizm zatrzymywał się natychmiast, w obrębie samego tytułu -
  zanim dotarł do linii z ceną, metrażem i adresem ("Warszawa..."). Brak
  słowa "Warszawa" w tak okrojonym tekście powodował odrzucenie WSZYSTKIEGO
  przez filtr miasta. Potwierdzone bezpośrednim testem na realistycznej
  karcie ogłoszenia (patrz find_card_text / TOTAL_PRICE_STOP_RE).
  Naprawa: cena za metr (rozpoznawana po "zł" bezpośrednio przed "/m") jest
  teraz wyłączona z liczenia "sygnału drugiej karty".

Przy okazji: nazwy ulic w config.json są już przechowywane BEZ prefiksu
"Ul."/"Al."/"Pl." (samo "Kasprowicza", nie "Ul. Kasprowicza") i dopasowanie
szuka tego jako fragmentu tekstu - więc złapie zarówno "Kasprowicza", jak i
"ul. Kasprowicza" w ogłoszeniu. To już działało poprawnie i zostało
zweryfikowane testem, żeby mieć pewność, że kolejne poprawki tego nie zepsują.

BŁĄD 3: "pokazują się oferty sprzed roku (np. 2024)"
  Przyczyna: skaner w ogóle nie sprawdzał FAKTYCZNEJ daty ogłoszenia - polegał
  wyłącznie na tym, że portal "zwykle" sortuje po dacie. Tabelaofert.pl
  (agregator) w ogóle nie filtruje po dacie - pokazuje WSZYSTKIE aktualne
  ogłoszenia dla danej ulicy, niezależnie jak stare. Dlatego, zgodnie z
  prośbą, Tabelaofert.pl został usunięty z listy portali.
  Naprawa: dodano dwuetapową weryfikację daty - (a) jeśli karta ogłoszenia
  na liście ma widoczny znacznik typu "Dodane dzisiaj"/"Dodane 3 dni temu",
  używamy go od razu bez dodatkowego zapytania; (b) jeśli nie ma takiego
  znacznika, dla kandydatów, które i tak przeszły już filtr ulicy/ceny/
  metrażu (więc jest ich mało), skaner otwiera stronę samego ogłoszenia
  i szuka tam etykiety typu "Data dodania"/"Ostatnia aktualizacja". Jeśli
  znajdzie jednoznacznie starą datę - odrzuca ogłoszenie.

BŁĄD 4: "pokazują się oferty np. z Wrocławia"
  Przyczyna: brakowało twardej blokady miasta - jeśli tekst wokół linku nie
  wspominał "Warszawa" wcale, nic tego nie odrzucało.
  Naprawa: każdy kandydat MUSI mieć w swoim tekście słowo "Warszawa" -
  w przeciwnym razie jest odrzucany, niezależnie od pozostałych dopasowań.

Portale (w kolejności priorytetu - ważniejsze skanowane najpierw, więc jeśli
budżet czasu się skończy, to mniej ważne portale ucierpią jako pierwsze):
Otodom.pl, Olx.pl, Nieruchomosci-online.pl, Adresowo.pl, Gratka.pl, Morizon.pl.

Pozostałe zasady działania (budżet czasu, portale bez wyszukiwania po ulicy
skanowane RAZ na cały przebieg, harmonogram co 24h) - bez zmian.
"""

import json
import os
import re
import time
import unicodedata
import urllib.parse
from datetime import date, datetime, timezone

import requests
from bs4 import BeautifulSoup

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
DATA_DIR = os.path.join(BASE_DIR, "data")
DATA_PATH = os.path.join(DATA_DIR, "listings.json")

MAX_RUNTIME_SECONDS = 18 * 60
DATE_VERIFICATION_BUFFER_DAYS = 3  # margines bezpieczeństwa ponad lookback_days

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "pl-PL,pl;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}
REQUEST_TIMEOUT = (5, 10)

PRICE_RE = re.compile(r"(\d[\d\s\u00a0]{2,9})\s?(?:zł|PLN)", re.IGNORECASE)
# Cena "za m2" (np. "19 714 zł/m2") też pasuje do PRICE_RE, ale to jedna
# dodatkowa liczba na KAŻDEJ, pojedynczej karcie (obok ceny całkowitej) - nie
# jest sygnałem, że zaczęliśmy zbierać tekst sąsiedniego ogłoszenia. Do
# wykrywania granicy między kartami liczymy więc tylko ceny NIE zaraz
# poprzedzające "/m" (czyli tylko cenę całkowitą).
TOTAL_PRICE_STOP_RE = re.compile(r"\d[\d\s\u00a0]{2,9}\s?zł(?!\s?/\s?m)", re.IGNORECASE)
AREA_RE = re.compile(r"(\d{1,3}(?:[.,]\d{1,2})?)\s?m(?:²|2|kw\.?)\b", re.IGNORECASE)
RENT_HINT_RE = re.compile(r"wynaj|/\s*mies|zł\s*/\s*miesi", re.IGNORECASE)
ADDRESS_RE = re.compile(
    r"((?:ul\.|al\.|pl\.|Aleja|Plac)\s*[^,]{2,40}(?:,\s*[^,]{2,40}){1,3},\s*Warszawa)",
    re.IGNORECASE,
)
AGE_HINT_RE = re.compile(r"dodane?\s+(dzisiaj|wczoraj|\d+\s*dni?\s*temu)", re.IGNORECASE)
DATE_LABEL_RE = re.compile(
    r"(?:Data dodania|Dodano|Opublikowano|Data publikacji|Data wystawienia|"
    r"Ostatnia aktualizacja|Aktualizacja)\s*[:\-]?\s*(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{2,4})",
    re.IGNORECASE,
)

WARSAW_DISTRICTS = [
    "Śródmieście", "Mokotów", "Ochota", "Wola", "Żoliborz", "Praga-Południe",
    "Praga-Północ", "Ursynów", "Wilanów", "Włochy", "Bielany", "Bemowo",
    "Ursus", "Wawer", "Wesoła", "Białołęka", "Targówek", "Rembertów",
]
WARSAW_DISTRICTS_AND_NAV_WORDS = {
    "wawer", "ursus", "ursynow", "wola", "mokotow", "praga-poludnie",
    "praga-polnoc", "pragapoludnie", "pragapolnoc", "bialoleka", "bielany",
    "bemowo", "ochota", "rembertow", "srodmiescie", "targowek", "wesola",
    "wilanow", "wlochy", "zoliborz", "warszawa", "mieszkania", "mieszkanie",
    "sprzedaz", "sprzedam", "wynajem", "wtorny", "pierwotny", "nowe",
    "oferty", "oferta", "wyniki", "ceny", "szukaj", "wyszukaj", "filtry",
    "regulamin", "kontakt", "pomoc", "logowanie", "rejestracja", "blog",
    "artykuly", "poradnik", "mapa-strony", "polityka-prywatnosci", "cookie",
}

session = requests.Session()
session.headers.update(HEADERS)
_run_start_time = time.monotonic()


def log(msg):
    print(f"[{datetime.now(timezone.utc).isoformat(timespec='seconds')}] {msg}", flush=True)


def time_budget_exceeded():
    return (time.monotonic() - _run_start_time) > MAX_RUNTIME_SECONDS


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def load_existing_data():
    if os.path.exists(DATA_PATH):
        try:
            with open(DATA_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            log("UWAGA: nie udało się odczytać istniejącego data/listings.json - zaczynam od zera.")
    return {"meta": {}, "listings": []}


def save_data(data):
    os.makedirs(DATA_DIR, exist_ok=True)
    data["listings"].sort(key=lambda x: x.get("first_seen", ""), reverse=True)
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def normalize(text):
    text = text.replace("\u00a0", " ")
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()


def slugify(text):
    text = normalize(text)
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def safe_get(url, timeout=REQUEST_TIMEOUT):
    try:
        resp = session.get(url, timeout=timeout)
        if resp.status_code == 200 and resp.text:
            return resp.text
        log(f"  -> HTTP {resp.status_code} dla {url}")
    except requests.RequestException as e:
        log(f"  -> błąd pobierania {url}: {e}")
    return None


def parse_price(text):
    m = PRICE_RE.search(text)
    if not m:
        return None
    digits = re.sub(r"[\s\u00a0]", "", m.group(1))
    try:
        return int(digits)
    except ValueError:
        return None


def parse_area(text):
    m = AREA_RE.search(text)
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", "."))
    except ValueError:
        return None


def extract_location_line(text):
    m = ADDRESS_RE.search(text)
    return m.group(1).strip() if m else None


def find_district(text):
    """Szuka nazwy dzielnicy Warszawy gdziekolwiek w tekście - niezależnie od
    dokładnej interpunkcji/kolejności, w jakiej dany portal ją zapisuje."""
    norm = normalize(text)
    for d in WARSAW_DISTRICTS:
        if normalize(d) in norm:
            return d
    return None


def mentions_warsaw(text):
    return "warszawa" in normalize(text)


def age_days_from_hint(text):
    """Próbuje odczytać wiek ogłoszenia wprost z karty na liście wyników
    (np. 'Dodane dzisiaj', 'Dodane 3 dni temu') - bez dodatkowego zapytania."""
    m = AGE_HINT_RE.search(text)
    if not m:
        return None
    token = m.group(1).lower()
    if token == "dzisiaj":
        return 0
    if token == "wczoraj":
        return 1
    num_m = re.search(r"\d+", token)
    return int(num_m.group()) if num_m else None


def extract_listing_date(text):
    m = DATE_LABEL_RE.search(text)
    if not m:
        return None
    day, month, year = m.groups()
    year = int(year)
    if year < 100:
        year += 2000
    try:
        return date(year, int(month), int(day))
    except ValueError:
        return None


def is_probable_offer_url(url, portal_name):
    """Czy adres URL wygląda na KONKRETNE ogłoszenie, a nie stronę
    kategorii/nawigacji (np. listę wszystkich ofert w danej dzielnicy)?"""
    parsed = urllib.parse.urlparse(url)
    path = parsed.path.lower().rstrip("/")
    if not path:
        return False

    last_segment = path.rsplit("/", 1)[-1]
    last_segment_clean = re.sub(r"\.(html?|php)$", "", last_segment)

    if last_segment_clean in WARSAW_DISTRICTS_AND_NAV_WORDS:
        return False

    if "otodom.pl" in parsed.netloc:
        return "/pl/oferta/" in path and bool(re.search(r"-id[a-z0-9]+", path))

    if "olx.pl" in parsed.netloc:
        return path.endswith(".html") and bool(re.search(r"id[a-z0-9]{4,}", last_segment_clean))

    has_id = bool(re.search(r"\d{5,}", last_segment_clean)) or bool(re.search(r"-id[a-z0-9]+", path))
    descriptive_slug = last_segment_clean.count("-") >= 2 or len(last_segment_clean) >= 20
    return has_id and descriptive_slug


def find_card_text(anchor, max_hops=8):
    """
    Rozszerza kontener tekstowy wokół linku krok po kroku. Zatrzymuje się,
    gdy w zebranym tekście pojawia się DRUGA cena CAŁKOWITA (TOTAL_PRICE_STOP_RE
    już poprawnie pomija cenę za m2, która i tak występuje raz na każdej,
    pojedynczej karcie) - to sygnał, że zaczęliśmy zbierać tekst sąsiedniej
    karty ogłoszenia.
    """
    container = anchor
    best_text = anchor.get_text(" ", strip=True)
    for _ in range(max_hops):
        parent = container.parent
        if parent is None:
            break
        candidate_text = parent.get_text(" ", strip=True)
        if len(TOTAL_PRICE_STOP_RE.findall(candidate_text)) >= 2:
            break
        best_text = candidate_text
        container = parent
    return best_text


def extract_listings(html, base_url, portal_name, min_area, max_area, min_price, max_price):
    soup = BeautifulSoup(html, "html.parser")
    results = []
    seen_urls = set()

    for a in soup.find_all("a", href=True):
        full_url = urllib.parse.urljoin(base_url, a["href"])
        if full_url in seen_urls:
            continue
        if not is_probable_offer_url(full_url, portal_name):
            continue

        text_block = find_card_text(a)

        if not mentions_warsaw(text_block):
            continue  # BŁĄD 4 - twarda blokada innych miast (np. Wrocławia)
        if RENT_HINT_RE.search(text_block):
            continue

        title = a.get_text(" ", strip=True) or (a.get("title") or "")
        if not title or len(title) < 3:
            title = text_block[:80]

        price = parse_price(text_block)
        area = parse_area(text_block)
        location = extract_location_line(text_block)

        if area is not None and not (min_area <= area <= max_area):
            continue
        if price is not None and not (min_price <= price <= max_price):
            continue

        seen_urls.add(full_url)
        results.append({
            "url": full_url,
            "title": title[:200],
            "price": price,
            "area": area,
            "location": location,
            "district": find_district(text_block),
            "match_text": normalize(f"{title} {location or ''}"),
            "age_hint_days": age_days_from_hint(text_block),
        })
    return results


def matching_streets(item, streets):
    return [s for s in streets if normalize(s["match"]) in item["match_text"]]


def within_criteria(item, criteria):
    if item.get("price") is not None and not (criteria["price_min_pln"] <= item["price"] <= criteria["price_max_pln"]):
        return False
    if item.get("area") is not None and not (criteria["area_min_m2"] <= item["area"] <= criteria["area_max_m2"]):
        return False
    return True


def is_too_old(item, lookback_days, run_settings):
    """
    BŁĄD 3 - weryfikacja daty. Zwraca True TYLKO gdy mamy jednoznaczny dowód,
    że ogłoszenie jest starsze niż lookback_days (+margines). W razie
    wątpliwości (brak daty) - NIE odrzucamy (lepiej pokazać niepewną ofertę
    niż zgubić prawdziwie nową).
    """
    max_age = lookback_days + DATE_VERIFICATION_BUFFER_DAYS
    if item.get("age_hint_days") is not None:
        return item["age_hint_days"] > max_age

    if time_budget_exceeded():
        return False  # brak czasu na dodatkową weryfikację - nie odrzucamy

    html = safe_get(item["url"])
    time.sleep(run_settings["request_delay_seconds"])
    if not html:
        return False
    text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
    listing_date = extract_listing_date(text)
    if listing_date is None:
        return False
    age_days = (date.today() - listing_date).days
    return age_days > max_age


def facebook_manual_link():
    return (
        "https://www.facebook.com/marketplace/warszawa/search"
        "?query=" + urllib.parse.quote("mieszkanie sprzedaż") + "&sortBy=creation_time_descend"
    )


def add_matches(data, existing_urls, criteria, matches, now_iso, counters, run_settings,
                 lookback_days, strict=False):
    added = 0
    skipped_old = 0
    for it in matches:
        if it["url"] in existing_urls:
            continue
        if not within_criteria(it, criteria):
            continue
        if strict and (it.get("price") is None or it.get("area") is None):
            continue
        if is_too_old(it, lookback_days, run_settings):
            skipped_old += 1
            continue
        existing_urls.add(it["url"])
        needs_review = it.get("price") is None or it.get("area") is None
        data["listings"].append({
            "url": it["url"],
            "title": it["title"],
            "price": it.get("price"),
            "area": it.get("area"),
            "location": it.get("location"),
            "district": it.get("district"),
            "portal": it["portal"],
            "street": it["street"],
            "first_seen": now_iso,
            "read": False,
            "needs_review": needs_review,
        })
        added += 1
    counters["new"] += added
    counters["skipped_old"] += skipped_old
    return added


# ---------------------------------------------------------------------------
# Adaptery "raz na cały skan"
# ---------------------------------------------------------------------------

def scan_otodom_once(streets, criteria, run_settings, is_first_run):
    matches = []
    max_pages = run_settings["otodom_pages_first_run"] if is_first_run else run_settings["otodom_pages_daily"]
    # Adres potwierdzony bezpośrednim sprawdzeniem na żywej stronie (2026-09):
    # przecinek między "mieszkanie" i "rynek-wtorny", BEZ powtórzenia "warszawa".
    # Poprzednia wersja miała błędny adres (.../warszawa/warszawa/warszawa), przez
    # co Otodom po cichu zwracał 0 ogłoszeń dla nierozpoznanej lokalizacji -
    # bez błędu HTTP, więc nic tego nie sygnalizowało w logach.
    base_search = "https://www.otodom.pl/pl/wyniki/sprzedaz/mieszkanie,rynek-wtorny/mazowieckie/warszawa"
    for page in range(1, max_pages + 1):
        if time_budget_exceeded():
            log("  -> przekroczono budżet czasu, przerywam Otodom wcześniej")
            break
        params = "by=LATEST&direction=DESC" + (f"&page={page}" if page > 1 else "")
        url = f"{base_search}?{params}"
        html = safe_get(url)
        time.sleep(run_settings["request_delay_seconds"])
        if not html:
            break
        items = extract_listings(html, url, "Otodom.pl", criteria["area_min_m2"], criteria["area_max_m2"],
                                  criteria["price_min_pln"], criteria["price_max_pln"])
        if not items:
            break
        for it in items:
            for street in matching_streets(it, streets):
                m = dict(it)
                m["portal"] = "Otodom.pl"
                m["street"] = street["display"]
                matches.append(m)
    return matches


def scan_heuristic_portal_once(portal, streets, criteria, run_settings):
    matches = []
    max_pages = run_settings["generic_pages_per_portal"]
    for base_url in portal.get("search_url_candidates", []):
        if time_budget_exceeded():
            break
        got_any = False
        for page in range(1, max_pages + 1):
            if time_budget_exceeded():
                break
            url = base_url if page == 1 else f"{base_url}?page={page}"
            html = safe_get(url)
            time.sleep(run_settings["request_delay_seconds"])
            if not html or len(html) < 500:
                break
            items = extract_listings(html, url, portal["name"], criteria["area_min_m2"], criteria["area_max_m2"],
                                      criteria["price_min_pln"], criteria["price_max_pln"])
            if not items:
                break
            got_any = True
            for it in items:
                for street in matching_streets(it, streets):
                    m = dict(it)
                    m["portal"] = portal["name"]
                    m["street"] = street["display"]
                    matches.append(m)
        if got_any:
            break
    return matches


# ---------------------------------------------------------------------------
# Adaptery "raz na ulicę" (portal wspiera wyszukiwanie po ulicy w URL-u)
# ---------------------------------------------------------------------------

def scan_olx_per_street(street, criteria, run_settings):
    query = urllib.parse.quote(street["match"])
    url = (
        "https://www.olx.pl/nieruchomosci/mieszkania/sprzedaz/warszawa/"
        f"?q={query}"
        f"&search%5Bfilter_float_price%3Ato%5D={criteria['price_max_pln']}"
        f"&search%5Bfilter_float_price%3Afrom%5D={criteria['price_min_pln']}"
        f"&search%5Bfilter_float_m%3Afrom%5D={criteria['area_min_m2']}"
        f"&search%5Bfilter_float_m%3Ato%5D={criteria['area_max_m2']}"
        "&search%5Bfilter_enum_market%5D%5B0%5D=secondary"
    )
    html = safe_get(url)
    time.sleep(run_settings["request_delay_seconds"])
    if not html:
        return []
    items = extract_listings(html, url, "Olx.pl", criteria["area_min_m2"], criteria["area_max_m2"],
                              criteria["price_min_pln"], criteria["price_max_pln"])
    for it in items:
        it["portal"] = "Olx.pl"
        it["street"] = street["display"]
    return items


def scan_adresowo_per_street(street, criteria, run_settings):
    slug = slugify(street["match"])
    url = f"https://adresowo.pl/mieszkania/warszawa/ul-{slug}-k/"
    html = safe_get(url)
    time.sleep(run_settings["request_delay_seconds"])
    if not html:
        return []
    items = extract_listings(html, url, "Adresowo.pl", criteria["area_min_m2"], criteria["area_max_m2"],
                              criteria["price_min_pln"], criteria["price_max_pln"])
    for it in items:
        it["portal"] = "Adresowo.pl"
        it["street"] = street["display"]
    return items


# ---------------------------------------------------------------------------
# Główna logika
# ---------------------------------------------------------------------------

def run():
    global _run_start_time
    _run_start_time = time.monotonic()

    config = load_config()
    data = load_existing_data()
    criteria = config["search_criteria"]
    run_settings = config["run_settings"]
    streets = config["streets"]

    is_first_run = len(data.get("listings", [])) == 0
    lookback_days = run_settings["first_run_lookback_days"] if is_first_run else run_settings["subsequent_run_lookback_days"]
    log(f"Start skanowania. Pierwsze uruchomienie: {is_first_run}. Horyzont: {lookback_days} dni. "
        f"Budżet czasu: {MAX_RUNTIME_SECONDS}s. Portale (wg priorytetu): {[p['name'] for p in config['portals']]}")

    existing_urls = {item["url"] for item in data.get("listings", [])}
    now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")
    counters = {"new": 0, "skipped_old": 0}
    errors = []
    timed_out = False

    for portal in config["portals"]:
        if not portal.get("enabled", True):
            continue
        if time_budget_exceeded():
            timed_out = True
            log("Przekroczono globalny budżet czasu - pomijam pozostałe (niżej priorytetowe) portale.")
            break

        log(f"Portal: {portal['name']} (adapter: {portal.get('adapter')})")
        try:
            if portal["name"] == "Otodom.pl":
                matches = scan_otodom_once(streets, criteria, run_settings, is_first_run)
                add_matches(data, existing_urls, criteria, matches, now_iso, counters, run_settings,
                            lookback_days, strict=False)

            elif portal["name"] == "Olx.pl":
                for street in streets:
                    if time_budget_exceeded():
                        timed_out = True
                        break
                    matches = scan_olx_per_street(street, criteria, run_settings)
                    add_matches(data, existing_urls, criteria, matches, now_iso, counters, run_settings,
                                lookback_days, strict=False)

            elif portal["name"] == "Adresowo.pl":
                for street in streets:
                    if time_budget_exceeded():
                        timed_out = True
                        break
                    matches = scan_adresowo_per_street(street, criteria, run_settings)
                    add_matches(data, existing_urls, criteria, matches, now_iso, counters, run_settings,
                                lookback_days, strict=False)

            else:  # portale "heurystyczne": Nieruchomosci-online, Gratka, Morizon
                matches = scan_heuristic_portal_once(portal, streets, criteria, run_settings)
                add_matches(data, existing_urls, criteria, matches, now_iso, counters, run_settings,
                            lookback_days, strict=True)

        except Exception as e:
            errors.append(f"{portal['name']}: {e}")
            log(f"  -> BŁĄD: {e}")
            continue

    data.setdefault("meta", {})
    data["meta"]["last_run"] = now_iso
    data["meta"]["last_run_new_listings"] = counters["new"]
    data["meta"]["last_run_skipped_old"] = counters["skipped_old"]
    data["meta"]["last_run_errors"] = errors
    data["meta"]["last_run_timed_out"] = timed_out
    data["meta"]["facebook_manual_search_url"] = facebook_manual_link()
    data["meta"]["criteria"] = criteria
    data["meta"]["total_listings"] = len(data["listings"])

    save_data(data)
    elapsed = round(time.monotonic() - _run_start_time)
    log(f"Zakończono w {elapsed}s. Nowych ofert: {counters['new']}. Odrzucono jako zbyt stare: "
        f"{counters['skipped_old']}. Błędów: {len(errors)}. Przekroczono budżet czasu: {timed_out}. "
        f"Razem w bazie: {len(data['listings'])}.")
    if errors:
        log("Szczegóły błędów (nie przerwały skanu):")
        for e in errors[:20]:
            log(f"  - {e}")


if __name__ == "__main__":
    run()
