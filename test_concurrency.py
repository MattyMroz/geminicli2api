"""
Test współbieżności serwera proxy.

Wysyła 4 równoległe requesty asynchronicznie.
Jeśli serwer obsługuje je współbieżnie, wszystkie powinny:
  - pojawić się w logach serwera prawie jednocześnie
  - zakończyć się w w zbliżonym czasie (nie sekwencyjnie)

Użycie:  uv run python test_concurrency.py
"""
import asyncio
import time
import httpx


PROXY_URL = "http://127.0.0.1:8888"
API_KEY = "123456"
MODEL = "gemini-2.5-flash"
CONCURRENT = 4


async def send_request(client: httpx.AsyncClient, req_id: int) -> dict:
    """Wyślij jedno krótkie zapytanie i zmierz czas."""
    start = time.perf_counter()
    prompt = f"Odpowiedz jednym słowem. Jaka jest liczba: {req_id * 111}? (request #{req_id})"

    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.0,
        "max_tokens": 32,
        "stream": False,
    }

    try:
        resp = await client.post(
            f"{PROXY_URL}/v1/chat/completions",
            json=payload,
            headers={
                "Authorization": f"Bearer {API_KEY}",
                "Content-Type": "application/json",
            },
            timeout=120.0,
        )
        elapsed = time.perf_counter() - start
        status = resp.status_code
        text = ""
        if status == 200:
            data = resp.json()
            choices = data.get("choices", [])
            if choices:
                text = choices[0].get("message", {}).get("content", "")[:80]
        else:
            text = resp.text[:120]

        return {"id": req_id, "status": status, "time": elapsed, "response": text}

    except Exception as e:
        elapsed = time.perf_counter() - start
        return {"id": req_id, "status": "ERROR", "time": elapsed, "response": str(e)[:120]}


async def main():
    print(f"\n{'='*60}")
    print(f"TEST WSPÓŁBIEŻNOŚCI SERWERA PROXY")
    print(f"Wysyłam {CONCURRENT} równoległych requestów...")
    print(f"{'='*60}\n")

    async with httpx.AsyncClient() as client:
        total_start = time.perf_counter()

        # Uruchom wszystkie requesty naraz
        tasks = [send_request(client, i + 1) for i in range(CONCURRENT)]
        results = await asyncio.gather(*tasks)

        total_elapsed = time.perf_counter() - total_start

    # Wyświetl wyniki
    print(f"\n{'='*60}")
    print(f"WYNIKI:")
    print(f"{'='*60}")
    for r in sorted(results, key=lambda x: x["id"]):
        print(
            f"  Request #{r['id']}:  status={r['status']}  czas={r['time']:.2f}s  odpowiedź: {r['response']}")

    times = [r["time"] for r in results]
    print(f"\n  Najszybszy: {min(times):.2f}s")
    print(f"  Najwolniejszy: {max(times):.2f}s")
    print(f"  Całkowity czas: {total_elapsed:.2f}s")

    # Jeśli sekwencyjne: total ≈ sum(times)
    # Jeśli równoległe: total ≈ max(times)
    sum_times = sum(times)
    if total_elapsed < sum_times * 0.7:
        print(
            f"\n  ✓ WSPÓŁBIEŻNOŚĆ DZIAŁA! (total {total_elapsed:.1f}s << suma {sum_times:.1f}s)")
    else:
        print(
            f"\n  ✗ BRAK WSPÓŁBIEŻNOŚCI! (total {total_elapsed:.1f}s ≈ suma {sum_times:.1f}s)")
        print(f"    Requesty były przetwarzane sekwencyjnie!")

    print(f"{'='*60}\n")


if __name__ == "__main__":
    asyncio.run(main())
