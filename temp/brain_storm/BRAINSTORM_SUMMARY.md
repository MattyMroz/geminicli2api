# BRAINSTORM — PODSUMOWANIE
## geminicli2api v2.0

---

### Stan projektu (7/10)

Darmowy, lokalny proxy serwer Google Gemini API z multi-account OAuth round-robin.
OpenAI-compatible + native Gemini endpoints. Zintegrowany translator SRT.

### Co działa

- 6 zweryfikowanych modeli (5/6 returnuje 200, gemini-3-pro-preview 429 = Google capacity)
- 20 wariantów modeli (search, nothinking, maxthinking)
- Multi-account rotation (3 konta, thread-safe Lock)
- Streaming SSE + non-streaming
- SRT batch translation z concurrent requests
- CLI: `--translate`, `--add-account`, `--list-models`
- System prompt → Gemini systemInstruction mapping
- Thinking budget control (per-model, reasoning_effort)
- Google Search grounding (-search suffix)

### Co naprawiono w tej sesji

1. Usunięto 7 wycofanych modeli (404 z Google API)
2. Dodano timeouty (connect=30s, read=300s, stream=600s)
3. Request ID tracking (UUID[:8]) na wszystkich logach
4. JSON error responses zamiast plain text
5. Write lock na subs.save() w translatorze
6. shutil.copy2 baseline copy przed tłumaczeniem
7. MAX_RETRIES 100→10 w translatorze
8. onboard_user timeout 120s (był infinite loop)
9. systemInstruction poprawnie mapowane (role: "user")
10. thinkingConfig tylko dla modeli z thinking support
11. removesuffix zamiast rstrip (fixing "gemini-2.5-flas" bug)
12. Password masking w logach

### Top 5 priorytetów

| # | Priorytet | Czas | Wpływ |
|---|-----------|------|-------|
| 1 | Fix race conditions (token refresh/save in lock) | 2h | Krytyczny |
| 2 | Replace requests → httpx (async native) | 4h | Wydajność |
| 3 | Unit testy (50+ testów) | 8h | Jakość |
| 4 | Docker containerization | 4h | Deployment |
| 5 | Web UI dashboard | 2 tyg | UX |

### Kluczowe metryki

| Metryka | Wartość |
|---------|---------|
| Pliki źródłowe | 16 |
| LOC | ~2910 |
| Modele bazowe | 6 |
| Warianty | 20 |
| Konta OAuth | 3 |
| Pokrycie testami | ~5% |
| Testy integracyjne | 2 skrypty |

### Architektura (warstwy)

```
CLI → FastAPI → Auth → Router → Transformer → API Client → Google CodeAssist
                                                    ↑
                                        AccountsManager (round-robin)
```

### Znane problemy !ZROBIONE!

- **Krytyczne**: Token refresh outside Lock (race condition), auth globals bez sync
- **Wysokie**: No connection pooling (requests), busy-wait streaming poll
- **Średnie**: datetime.utcfromtimestamp deprecated, catch-all route, hardcoded port

### Roadmap

- **v2.1** (2-4 tyg): Fix races, httpx, unit tests, structured logging !ZROBIONE!
- **v3.0** (1-3 mies): Admin dashboard, caching, rate limiting, metrics
- **v4.0** (3-6 mies): Docker, Web UI translator, multi-provider, SDK

---

*Pełna wersja: temp/brain_storm/BRAINSTORM.md (~1000 linii)*
