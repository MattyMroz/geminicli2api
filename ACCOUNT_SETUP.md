# Wymagania konta Google

## Co musi być spełnione żeby konto działało

### 1. Konto Google z zaakceptowanymi warunkami

Konto musi być w pełni aktywne — nie może być nowe bez żadnej historii.
Google czasem żąda weryfikacji telefonu przed pierwszym użyciem API.

### 2. Weryfikacja konta (telefon)

Jeśli `test_accounts.py` wyświetla:

```
Wymagana weryfikacja konta Google
Otworz w przegladarce (zalogowany na to konto):
https://accounts.google.com/signin/continue?...
```

Trzeba otworzyć ten link w przeglądarce **zalogowanej na to konkretne konto Google** i przejść weryfikację (zwykle SMS na numer telefonu przypisany do konta).

Po weryfikacji konto działa od razu.

### 3. Onboarding Gemini Code Assist

Konto musi być zarejestrowane w programie **Gemini Code Assist for individuals** (free tier).
Odbywa się to automatycznie przy `uv run start.py -a` — nie trzeba nic robić ręcznie.

Jeśli konto nie zostało onboardowane (brak `project_id` w pliku JSON), `test_accounts.py` próbuje to naprawić automatycznie podczas testu.

### 4. Plik JSON z `project_id`

Każdy plik `accounts/account_N.json` musi zawierać pole `project_id`.
Jest ono zapisywane automatycznie po onboardingu.

Przykład poprawnego pliku:
```json
{
  "client_id": "...",
  "client_secret": "...",
  "token": "...",
  "refresh_token": "...",
  "project_id": "nazwa-projektu-xxxxx"
}
```

---

## Kolejność działań przy dodawaniu nowego konta

1. `uv run start.py -a` — OAuth w przeglądarce, automatyczny onboarding
2. `uv run test_accounts.py N` — sprawdź czy konto działa
3. Jeśli wymagana weryfikacja — otwórz podany link, zweryfikuj telefon, powtórz test

---

## Typowe błędy

| Błąd | Przyczyna | Rozwiązanie |
|------|-----------|-------------|
| `Wymagana weryfikacja konta Google` | Konto nie zweryfikowane | Otwórz link z testu w przeglądarce |
| `Brak cloudaicompanionProject w odpowiedzi` | Konto nie onboardowane | Uruchom `uv run start.py -a` dla tego konta |
| `brak refresh_token` | Uszkodzony plik JSON | Usuń plik i dodaj konto od nowa przez `-a` |
| `403 Forbidden` (inne) | Przekroczony limit lub zbanowane konto | Sprawdź konto w Google Cloud Console |
