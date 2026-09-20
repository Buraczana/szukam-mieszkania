# Szukam mieszkania — monitor ofert

## ⚠️ Kolejna aktualizacja — stare oferty (np. z 2024) i oferty spoza Warszawy

Zgłoszone problemy: **(1)** pokazywały się oferty sprzed roku i **(2)** pojedyncze
oferty z innych miast (np. Wrocławia).

**Przyczyny i poprawki:**
1. Skaner w ogóle nie sprawdzał daty ogłoszenia - polegał tylko na tym, że
   portal "zwykle" pokazuje najnowsze najpierw. **Tabelaofert.pl został
   usunięty** (jak prosiłaś) - jako agregator w ogóle nie filtruje po dacie,
   stąd stare wyniki. Dodałam też właściwą weryfikację daty: jeśli karta
   ogłoszenia ma widoczny znacznik „Dodane dzisiaj"/„Dodane X dni temu",
   skaner go używa; jeśli nie, dla nielicznych kandydatów, które i tak już
   przeszły resztę filtrów, otwiera samo ogłoszenie i sprawdza tam datę.
   Jednoznacznie stare ogłoszenia są odrzucane.
2. Brakowało twardej blokady miasta. Teraz każdy kandydat MUSI mieć w swoim
   tekście słowo „Warszawa" - inaczej jest odrzucany, niezależnie od tego,
   czy nazwa ulicy przypadkiem pasuje.
3. **Nowa lista portali (wg priorytetu, ważniejsze skanowane najpierw):**
   Otodom.pl, OLX.pl, Nieruchomości-online.pl, Adresowo.pl (priorytet) →
   Gratka.pl, Morizon.pl (niższy priorytet - skanowane na końcu, więc jeśli
   kiedyś zabraknie czasu, to one ucierpią jako pierwsze, a nie priorytetowe).

### Jak wgrać tę poprawkę
Tak jak poprzednio: nadpisz `scraper.py`, `config.json` i **`data/listings.json`**
(ten ostatni czyści stare, błędne wyniki - w tym te z 2024 i z Wrocławia) i
uruchom skan ręcznie ponownie (Actions → Skanuj oferty mieszkań → Run workflow).

---

## ⚠️ Aktualizacja (poprawka błędów) — przeczytaj, jeśli aplikację masz już zainstalowaną

Zgłoszone problemy: **(1)** pokazywały się oferty z niechcianych dzielnic
(Wawer, Ursus, Praga-Północ) i **(2)** linki prowadziły do ogólnych stron
portali zamiast do konkretnych ogłoszeń.

**Przyczyna obu:** stary filtr uznawał za „ogłoszenie" każdy link zawierający
ogólne słowo typu „mieszkanie"/„oferty" — a takie słowa mają też linki
nawigacyjne portali w stylu „zobacz oferty w innych dzielnicach: Wawer, Ursus,
Praga-Północ...". Te linki prowadzą do ogólnych stron kategorii (nie do
konkretnego ogłoszenia), więc obce dzielnice brały się z bocznej nawigacji
portalu błędnie wziętej za wynik wyszukiwania — nie z Twoich ulic.

**Co naprawiłam:**
1. Każdy link jest teraz sprawdzany ściśle pod kątem tego, czy naprawdę
   wygląda jak konkretne ogłoszenie (unikalny numer/kod), a nie strona
   kategorii/dzielnicy — strony kategorii są odrzucane.
2. Tekst, z którego wyciągana jest cena/metraż/adres, jest teraz precyzyjnie
   ograniczony do jednej karty ogłoszenia (nie „zbiera" już przypadkiem danych
   sąsiedniego ogłoszenia z listy).
3. Zawężyłam skanowanie do **6 najważniejszych portali** (jak prosiłaś):
   Otodom.pl, OLX.pl, Tabelaofert.pl, Nieruchomosci-online.pl, Morizon.pl,
   Gratka.pl. Pierwsze trzy mają potwierdzony, stabilny wzorzec adresów
   ogłoszeń. Ostatnie trzy trzymam na bardziej rygorystycznych zasadach
   (patrz sekcja „Ograniczenia" niżej) — jeśli po tygodniu okaże się, że nic
   z nich nie przychodzi, adres wyszukiwania może wymagać korekty w
   `config.json`.
4. Dodałam w aplikacji linijkę „📍 Adres w ogłoszeniu" pod każdą pozycją —
   pokazuje dokładny adres, jaki portal podaje dla danego ogłoszenia, żebyś
   od razu mogła zweryfikować, że dopasowanie jest trafne.

### Jak wgrać poprawkę (masz już repozytorium na GitHubie)
1. W repozytorium wejdź kolejno w pliki `scraper.py`, `config.json`,
   `index.html`, `data/listings.json` i dla każdego kliknij ✏️ (Edit),
   zaznacz całą zawartość (Ctrl+A), usuń, wklej nową treść z tej paczki,
   **Commit changes**. (Albo prościej: **Add file → Upload files** i wgraj
   te same pliki ponownie — GitHub nadpisze istniejące).
2. Plik `data/listings.json` **specjalnie nadpisujemy pustą wersją** —
   usuwa to błędne stare wyniki (Wawer, Ursus itd.), które inaczej zostałyby
   w bazie na zawsze (deduplikacja działa po adresie URL, więc same by nie
   zniknęły).
3. Uruchom skan ręcznie: **Actions → Skanuj oferty mieszkań → Run workflow**.
   Zadziała jak pierwsze uruchomienie — zbierze znowu 7 dni wstecz, tym razem
   z poprawionym filtrowaniem.
4. Sprawdź kilka pierwszych wyników i porównaj „Szukana ulica" z „📍 Adres w
   ogłoszeniu" — powinny się zgadzać.

---

Aplikacja codziennie sama sprawdza wybrane portale z ogłoszeniami i pokazuje Ci
tylko **nowe** oferty mieszkań spełniające Twoje kryteria (konkretne ulice
Warszawy, 25–42 m², cena do 770 000 zł, rynek wtórny). Działa jak czytnik RSS:
nieprzeczytane są wyróżnione, klikasz „oznacz jako przeczytane" i znikają z
głównego widoku.

**Nie musisz niczego instalować na swoim komputerze.** Wszystko dzieje się na
serwerach GitHuba — Ty potrzebujesz tylko konta GitHub (masz) i przeglądarki.

---

## Jak to działa (krótkie wyjaśnienie)

- **Skaner** (`scraper.py`) to program w Pythonie, który raz na 24h automatycznie
  uruchamia się na serwerze GitHuba (funkcja „GitHub Actions") i przeszukuje
  portale wymienione w `config.json`.
- Wyniki trafiają do pliku `data/listings.json` w Twoim repozytorium.
- **Strona** (`index.html`) to widok tych danych — wystawiony w internecie za
  darmo przez „GitHub Pages". Otwierasz ją jak każdą stronę, także na telefonie.
- Stan „przeczytane/nieprzeczytane" zapisuje się lokalnie w Twojej przeglądarce
  (nie w repozytorium) — osobno dla telefonu i komputera.

---

## Instalacja krok po kroku

### 1. Załóż nowe repozytorium
Wejdź na [github.com/new](https://github.com/new). Nadaj nazwę np.
`szukam-mieszkania`, ustaw jako **Public** (patrz uwaga o prywatności na końcu),
nie zaznaczaj „Add a README" — kliknij **Create repository**.

### 2. Wgraj pliki
Rozpakuj paczkę, którą dostałaś, na swoim komputerze. W repozytorium na GitHubie
kliknij **Add file → Upload files** i przeciągnij tam **całą zawartość**
rozpakowanego folderu (łącznie z podfolderami `.github` i `data` — nowoczesny
GitHub zachowuje strukturę folderów przy przeciąganiu). Na dole kliknij
**Commit changes**.

Jeśli `.github` nie chce się przeciągnąć jako folder, możesz też dodać
pojedynczy plik: **Add file → Create new file**, w polu nazwy wpisz od razu
`.github/workflows/scan.yml` (ukośniki same utworzą foldery) i wklej zawartość.

### 3. Włącz uprawnienia zapisu dla Actions
Skaner musi mieć zgodę na zapisywanie wyników z powrotem do repozytorium.
Wejdź w **Settings → Actions → General**, przewiń do **Workflow permissions**,
zaznacz **Read and write permissions**, kliknij **Save**.

### 4. Włącz GitHub Pages
Wejdź w **Settings → Pages**. W sekcji „Build and deployment" przy **Source**
wybierz **Deploy from a branch**, a w **Branch** wybierz `main` i folder `/(root)`,
kliknij **Save**. Po minucie-dwóch GitHub pokaże Ci adres strony (coś w stylu
`https://twoja-nazwa.github.io/szukam-mieszkania/`) — zapisz go, dodasz go do
ekranu głównego telefonu.

### 5. Uruchom pierwsze skanowanie ręcznie
Wejdź w zakładkę **Actions**, po lewej kliknij **Skanuj oferty mieszkań**, po
prawej **Run workflow → Run workflow**. Odśwież po chwili — pojawi się żółte
kółko (trwa), a po **ok. 10–15 minutach** zielony ptaszek (gotowe). Skanowanie
ma wbudowany limit 25 minut, więc nie powinno nigdy trwać dłużej — jeśli
kiedyś zobaczysz żółte kółko dłużej niż pół godziny, to znak, że coś jest
nie tak (patrz „Rozwiązywanie problemów"). To pierwsze skanowanie zbiera
oferty **z ostatnich 7 dni**. Kolejne, automatyczne, będą już tylko dokładać
nowości co 24h.

### 6. Otwórz aplikację
Wejdź pod adres z kroku 4. Powinny być widoczne pierwsze znalezione oferty.
Na telefonie: w Safari/Chrome wybierz „Dodaj do ekranu głównego" — będzie
działać jak zwykła aplikacja.

---

## Codzienna obsługa

- Skaner sam odpala się codziennie ok. **6:00–7:00 czasu polskiego**.
- Na stronie widzisz tylko nieprzeczytane jako domyślny filtr — zmieniasz w
  rozwijanej liście „Tylko nieprzeczytane / Wszystkie".
- Klik w „Oznacz jako przeczytane" przy ofercie albo „Oznacz wszystkie" u góry.
- „sprawdź szczegóły" przy ofercie oznacza, że nie udało się automatycznie
  odczytać ceny lub metrażu ze strony wyników — otwórz ogłoszenie i sprawdź
  ręcznie, czy naprawdę pasuje.
- Facebook Marketplace: link do ręcznego sprawdzenia jest zawsze widoczny na
  górze strony (patrz „Ograniczenia" niżej — nie da się tego zautomatyzować
  wiarygodnie).

## Zmiana kryteriów, ulic albo portali
Wszystko jest w pliku `config.json`. W repozytorium na GitHubie kliknij ten
plik, potem ikonę ołówka (Edit), zmień np. `price_max_pln` albo dopisz/usuń
ulicę na liście `streets` (potrzebujesz pól `display` i `match`), zapisz
przez **Commit changes**. Zmiana zadziała od następnego skanowania (albo
uruchom je ręcznie jak w kroku 5).

---

## Uczciwe ograniczenia — przeczytaj, żeby wiedzieć, czego się spodziewać

1. **Otodom.pl, OLX.pl, Adresowo.pl** — potwierdzony, stabilny wzorzec
   adresów wyszukiwania i ogłoszeń, precyzyjne dopasowanie.
2. **Nieruchomości-online.pl** (priorytet), **Gratka.pl, Morizon.pl** (niższy
   priorytet) — duże, prawdziwe portale, ale bez potwierdzonego ze 100%
   pewnością adresu strony wyszukiwania, więc traktowane bardziej
   rygorystycznie: ogłoszenie musi mieć jednocześnie cenę I metraż w
   zakresie kryteriów, inaczej jest pomijane. Jeśli po tygodniu z któregoś
   nic nie przychodzi, otwórz `config.json`, znajdź `search_url_candidates`
   przy tym portalu i podmień na aktualny adres strony wyników wyszukiwania
   (wejdź na portal, ustaw filtry ręcznie, skopiuj adres z paska przeglądarki).
3. **Weryfikacja daty nie jest stuprocentowa.** Jeśli portal nie pokazuje
   nigdzie czytelnej daty dodania/aktualizacji (ani na liście, ani na stronie
   ogłoszenia), skaner nie ma jak stwierdzić wieku i **w razie wątpliwości
   pokazuje ofertę** (woli pokazać niepewną niż zgubić prawdziwie nową) — to
   rzadkie, ale może się zdarzyć.
4. **Strony renderowane dopiero w przeglądarce (JavaScript)** — skaner
   pobiera goły HTML, bez uruchamiania JavaScriptu.
5. **Facebook / Facebook Marketplace** celowo NIE jest automatycznie
   przeszukiwany (logowanie + zabezpieczenia antybotowe) — link do ręcznego
   sprawdzenia jest zawsze widoczny na górze strony.
6. **Rzadki przypadek: duplikaty nazw ulic** w różnych, niesąsiadujących
   dzielnicach Warszawy (pozostałość po przyłączeniu dawnych gmin) - dlatego
   każda pozycja pokazuje „📍 Adres w ogłoszeniu" do szybkiej weryfikacji.
7. **Zmieniające się strony portali** — jeśli portal przebuduje stronę,
   dopasowanie może się zepsuć. Daj znać, a poprawię odpowiedni fragment
   `scraper.py`.
8. To narzędzie **wspomaga** wyszukiwanie, ale przy tak ważnej decyzji jak
   zakup mieszkania warto też od czasu do czasu zerknąć na portale ręcznie.

## Prywatność
GitHub Pages w darmowym planie publikuje stronę pod publicznym (choć
nie promowanym nigdzie) adresem — każdy, kto pozna dokładny link, mógłby ją
zobaczyć. Nie zawiera danych osobowych ani finansowych, tylko listę ulic,
które Cię interesują, i linki do publicznych ogłoszeń. Jeśli wolisz, żeby
było to całkiem prywatne, GitHub oferuje prywatne Pages w płatnym planie
(GitHub Pro) — wtedy w kroku 4 repozytorium zakładasz jako **Private**.

## Rozwiązywanie problemów
- **Czerwony X w Actions zamiast zielonego ptaszka** — kliknij w to
  uruchomienie, potem w krok, który zawiódł, żeby zobaczyć komunikat błędu.
  Najczęstsza przyczyna: nie zaznaczono „Read and write permissions" (krok 3).
- **Strona pokazuje „Nie udało się wczytać danych"** — sprawdź, czy plik
  `data/listings.json` faktycznie jest w repozytorium (w głównym folderze,
  w podfolderze `data`).
- **Zero nowych ofert przez kilka dni** — to może być prawidłowe (rzadkie
  ulice + wąskie kryteria), sprawdź log skanowania, żeby zobaczyć, ile
  ogłoszeń w ogóle przejrzano na danym portalu.
