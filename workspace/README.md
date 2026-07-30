# Tłumaczenie napisów SRT metodą „chmury agentów”

Dokument opisuje, jak podszedłem do tłumaczenia plików napisów `Shadow Slave`
(EN → PL) z użyciem wielu równoległych subagentów. Metoda pozwala przetłumaczyć
duży plik szybko, dzieląc pracę na kawałki i uruchamiając agentów jednocześnie.

---

## Idea w skrócie

Zamiast tłumaczyć cały plik w jednym, długim przebiegu, dzielimy go na paczki
po **30 napisów** i każdą paczkę oddajemy **osobnemu subagentowi**. Każdy agent
dostaje **dokładnie ten sam prompt tłumaczeniowy** (pliki z instrukcjami czytane
w całości) i tłumaczy tylko swój wycinek. Agenci pracują **równolegle**, więc
czas tłumaczenia całego pliku ≈ czas najwolniejszego pojedynczego agenta.

Na końcu składamy wszystkie tłumaczenia z powrotem w plik SRT, zachowując
**oryginalną numerację i znaczniki czasu 1:1** — podmieniamy wyłącznie tekst.

```
plik.srt (N napisów)
   │
   ├─ parsowanie → lista (numer, timestamp, tekst)
   │
   ├─ podział na paczki po 30 → agent_01.txt … agent_XX.txt
   │
   ├─ N agentów RÓWNOLEGLE (ten sam prompt) → out_01.json … out_XX.json
   │
   ├─ walidacja (liczba elementów, brak podwójnych enterów)
   │
   └─ scalenie: numer + timestamp z oryginału + przetłumaczony tekst
              → nadpisanie plik.srt (numeracja i czasy nietknięte)
```

---

## Krok po kroku

### 1. Wczytanie promptów tłumaczeniowych
Prompt tłumaczeniowy to jeden lub dwa pliki tekstowe z zasadami (terminologia
świata, nazwy i płeć postaci, liczebniki słownie, usuwanie znaków wodnych,
formatowanie 1:1, ton pod audiobook). Każdy agent czyta je **w całości** —
to jego „instrukcja systemowa".

Użyte prompty:
- `apps/gemini_translator/prompts/prompt_helper.txt`
- `apps/gemini_translator/prompts/prompt_helperSS.txt`
  (lub `prompt_main.txt` — zależnie od zlecenia)

### 2. Parsowanie SRT
Plik SRT rozbijamy na bloki (rozdzielone pustą linią). Z każdego bloku
wyciągamy trójkę: **numer**, **timestamp** (`--> `) i **tekst**. Zapisujemy do
`parsed.json`.

### 3. Podział na paczki po 30 napisów
Napisy tniemy na paczki po 30 (ostatnia paczka może być mniejsza). Każda paczka
zapisywana jest jako plik `agent_NN.txt`, w którym napisy są ponumerowane
lokalnie `[1]`, `[2]`, … — dzięki temu agent wie, ile ma zwrócić elementów.

Przykład podziału pliku z 253 napisami:
```
agent_01: napisy 1-30   (30 szt.)
agent_02: napisy 31-60  (30 szt.)
...
agent_09: napisy 241-253 (13 szt.)
```

### 4. Uruchomienie agentów równolegle
Wszystkie subagenty startują **w jednej turze** (jednocześnie). Każdy dostaje
identyczne polecenie:
1. przeczytaj oba pliki promptów w całości,
2. przeczytaj swój `agent_NN.txt`,
3. przetłumacz wszystkie napisy na polski wg zasad,
4. zapisz wynik jako **czysty JSON**: `{"t": ["tłum. 1", "tłum. 2", ...]}`
   do `out_NN.json`,
5. zwróć tylko krótkie potwierdzenie (`OK NN, elementów: <liczba>`), a nie treść
   tłumaczenia (oszczędza kontekst głównej sesji).

**Model:** można użyć Opus (najwyższa jakość) lub Sonnet (szybciej, taniej).
Oba sprawdzają się w tym zadaniu.

### 5. Walidacja
Przed scaleniem sprawdzamy:
- czy każdy `out_NN.json` istnieje i jest poprawnym JSON-em,
- czy **suma elementów = liczbie napisów w oryginale** (np. 246),
- czy w żadnym tłumaczeniu nie ma **podwójnego entera `\n\n`** wewnątrz napisu —
  taki znak rozbiłby jeden napis na dwa bloki i rozjechał synchronizację z
  timestampami. Jeśli się pojawi (np. w miejscu przejścia między rozdziałami),
  zamieniamy go na spacje zgodnie z formatem oryginału.

### 6. Scalenie i nadpisanie
Sklejamy: **numer** i **timestamp** bierzemy z oryginału (`parsed.json`),
**tekst** z tłumaczeń (`out_*.json`), w tej samej kolejności. Zapisujemy w
kodowaniu **UTF-8** z końcówkami linii `\n`. Przed nadpisaniem robimy **kopię
zapasową** oryginału.

### 7. Weryfikacja końcowa
Po zapisie sprawdzamy, że:
- liczba bloków = liczbie napisów,
- numeracja jest ciągła (`1..N`),
- każdy blok ma timestamp.

---

## Kluczowe zasady jakości

- **Struktura 1:1** — nigdy nie ruszamy numerów ani znaczników czasu; zmienia
  się wyłącznie tekst.
- **Zgodność liczby napisów** — ile wchodzi, tyle wychodzi (agent zwraca
  dokładnie tyle elementów, ile dostał).
- **Ten sam prompt dla wszystkich** — spójna terminologia i nazwy postaci w
  całym pliku (wspólny słownik świata).
- **Płeć i rodzaj postaci** — pilnujemy poprawnego rodzaju gramatycznego wg
  słownika (np. `Nightwalker` = mężczyzna; `kohorta` = grupa mieszana, rodzaj
  męskoosobowy, a nie same kobiety).
- **Bez znaków wodnych** — fragmenty typu `novelfire.net`, `freewebnovel.com`
  i pochodne są usuwane, nie tłumaczone.
- **Pod audiobook** — liczby, skróty, procenty i waluty zapisywane słownie
  (np. `1%` → „jeden procent", `Chapter 3051` → „Rozdział trzy tysiące
  pięćdziesiąty pierwszy").

---

## Ograniczenia metody

- Każdy agent tłumaczy swój blok **niezależnie**, bez wglądu w sąsiednie paczki.
  Spójność terminologii jest zapewniona przez wspólny słownik, ale subtelny
  **styl** może się minimalnie różnić na styku paczek.
- Rozwiązanie: opcjonalny przebieg **jednego agenta-korektora** na całości, który
  ujednolica styl i wyłapuje literówki oraz błędy rodzaju/płci.
- Zawsze warto zrobić **szybki przegląd** krytycznych miejsc (przejścia
  rozdziałów, nazwy i płeć postaci) po scaleniu.

---

## Struktura plików roboczych

```
workspace/
├─ input/
│  └─ SS_XXXX-YYYY.srt          # plik źródłowy → nadpisany tłumaczeniem
├─ tem/  (lub tem2/, ...)       # katalog roboczy danego pliku
│  ├─ parsed.json               # sparsowany oryginał (numer, czas, tekst)
│  ├─ SS_XXXX-YYYY.backup.srt   # kopia zapasowa oryginału
│  └─ chunks/
│     ├─ agent_01.txt … agent_NN.txt   # paczki wejściowe dla agentów
│     └─ out_01.json … out_NN.json     # tłumaczenia zwrócone przez agentów
└─ README.md                    # ten dokument
```

---

## Historia wykonanych plików

| Plik                | Napisów | Podział          | Model     | Uwagi |
|---------------------|---------|------------------|-----------|-------|
| `SS_3026-3050.srt`  | 253     | 8×30 + 1×13      | Opus 4.8  | — |
| `SS_3051-3075.srt`  | 246     | 8×30 + 1×6       | Sonnet 5  | naprawiono 3 podwójne entery na przejściach rozdziałów; poprawiono płeć `Nightwalker` (mężczyzna) i rodzaj `kohorty` (grupa mieszana) |
