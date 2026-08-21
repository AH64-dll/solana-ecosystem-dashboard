#!/usr/bin/env python3
"""Fetch Solana ecosystem data from free public APIs and cache it as JSON.

Sources (all keyless):
  - api.llama.fi/v2/chains                  -> current TVL per chain
  - api.llama.fi/v2/historicalChainTvl/Solana -> full Solana TVL history
  - api.llama.fi/protocols                  -> protocol registry (filtered to Solana)
  - stablecoins.llama.fi/stablecoincharts/Solana -> stablecoin circulation history
  - api.coingecko.com/api/v3                -> SOL market data

Each dataset is written to data/<name>.json with fetched_at timestamps.
If a fetch fails, the previous cache is kept and flagged stale=true;
the script exits non-zero only if nothing could be produced at all.

Usage: python3 fetch_data.py [--outdir data]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

UA = {"User-Agent": "solana-ecosystem-dashboard/1.0 (open-source; contact: repo issues)"}
TIMEOUT = 45
RETRIES = 3


def http_get_json(url: str):
    """GET a JSON URL with retries. Returns parsed JSON or raises."""
    last_err = None
    for attempt in range(RETRIES):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError,
                json.JSONDecodeError, OSError) as err:
            last_err = err
            wait = 2 ** attempt * 2
            print(f"  ! attempt {attempt + 1}/{RETRIES} failed: {err}; retrying in {wait}s", flush=True)
            time.sleep(wait)
    raise RuntimeError(f"all {RETRIES} attempts failed for {url}: {last_err}")


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def save(outdir: Path, name: str, payload: dict) -> Path:
    path = outdir / f"{name}.json"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    tmp.replace(path)
    print(f"  ✓ wrote {path} ({path.stat().st_size / 1024:.1f} KB)", flush=True)
    return path


def load_cached(outdir: Path, name: str):
    path = outdir / f"{name}.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
    return None


# --------------------------------------------------------------------------
# Individual fetchers: each returns (payload_dict, ok_bool)
# --------------------------------------------------------------------------

def fetch_tvl_history() -> dict:
    """Full historical TVL for Solana + snapshot of every chain (for rank)."""
    hist = http_get_json("https://api.llama.fi/v2/historicalChainTvl/Solana")
    chains = http_get_json("https://api.llama.fi/v2/chains")
    points = [[int(p["date"]), round(float(p["tvl"]), 2)] for p in hist
              if p.get("date") and p.get("tvl") is not None]
    sol_tvl = points[-1][1] if points else None
    ranked = sorted(
        ({"name": c["name"], "tvl": round(float(c.get("tvl") or 0), 2),
          "tokenSymbol": c.get("tokenSymbol")} for c in chains),
        key=lambda c: c["tvl"], reverse=True)
    sol_rank = next((i + 1 for i, c in enumerate(ranked) if c["name"] == "Solana"), None)
    return {
        "fetched_at": now_iso(),
        "sources": ["api.llama.fi/v2/historicalChainTvl/Solana", "api.llama.fi/v2/chains"],
        "points": points,                      # [[unix_date, tvl_usd], ...]
        "current_tvl": sol_tvl,
        "chain_rank": sol_rank,
        "top_chains": ranked[:15],
        "total_chains_tracked": len(chains),
    }


def fetch_stablecoins() -> dict:
    """Stablecoin circulating supply on Solana over time."""
    raw = http_get_json("https://stablecoins.llama.fi/stablecoincharts/Solana")
    points = []
    for entry in raw:
        ts = entry.get("date")
        circ = entry.get("totalCirculatingUSD") or {}
        usd = circ.get("peggedUSD")
        if ts and usd is not None:
            points.append([int(ts), round(float(usd), 2)])
    return {
        "fetched_at": now_iso(),
        "source": "stablecoins.llama.fi/stablecoincharts/Solana",
        "points": points,                      # [[unix_date, circulating_usd], ...]
        "current": points[-1][1] if points else None,
    }


def fetch_market() -> dict:
    """SOL market stats from CoinGecko."""
    params = urllib.parse.urlencode({
        "vs_currency": "usd", "ids": "solana", "sparkline": "false",
        "price_change_percentage": "24h,7d,30d,1y",
        "per_page": "1", "page": "1",
    })
    data = http_get_json(f"https://api.coingecko.com/api/v3/coins/markets?{params}")
    if not data:
        raise RuntimeError("coingecko returned empty market list")
    c = data[0]
    keys = ("current_price", "market_cap", "market_cap_rank", "total_volume",
            "circulating_supply", "total_supply", "ath", "ath_change_percentage",
            "ath_date", "atl", "atl_date",
            "price_change_percentage_24h_in_currency",
            "price_change_percentage_7d_in_currency",
            "price_change_percentage_30d_in_currency",
            "price_change_percentage_1y_in_currency")
    out = {"fetched_at": now_iso(), "source": "api.coingecko.com/api/v3/coins/markets"}
    out.update({k: c.get(k) for k in keys})
    return out


def fetch_protocols(min_tvl_usd: float = 100_000.0, top_n: int = 50) -> dict:
    """Protocols deployed on Solana, ranked by their Solana-side TVL."""
    all_protocols = http_get_json("https://api.llama.fi/protocols")
    rows = []
    for p in all_protocols:
        tvls = p.get("chainTvls")
        if not isinstance(tvls, dict):
            continue
        sol_tvl = tvls.get("Solana")
        if not isinstance(sol_tvl, (int, float)) or sol_tvl < min_tvl_usd:
            continue
        rows.append({
            "name": p.get("name"),
            "symbol": p.get("symbol"),
            "category": p.get("category"),
            "tvl_solana": round(float(sol_tvl), 2),
            "tvl_total": round(float(p.get("tvl") or 0), 2),
            "change_1d": p.get("change_1d"),
            "change_7d": p.get("change_7d"),
            "change_1m": p.get("change_1m"),
            "url": p.get("url"),
            "listed_at": p.get("listedAt"),
        })
    rows.sort(key=lambda r: r["tvl_solana"], reverse=True)
    return {
        "fetched_at": now_iso(),
        "source": "api.llama.fi/protocols (filtered: chainTvls.Solana)",
        "protocol_count_on_solana": sum(
            1 for p in all_protocols
            if isinstance(p.get("chains"), list) and "Solana" in p["chains"]),
        "tracked_with_tvl": len(rows),
        "top": rows[:top_n],
    }


FETCHERS = {
    "tvl_history": fetch_tvl_history,
    "stablecoins": fetch_stablecoins,
    "market": fetch_market,
    "protocols": fetch_protocols,
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--outdir", default="data", help="cache directory (default: data)")
    args = ap.parse_args()
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    produced, failures = [], []
    for name, fn in FETCHERS.items():
        print(f"[{name}] fetching…", flush=True)
        try:
            payload = fn()
            save(outdir, name, payload)
            produced.append(name)
        except Exception as err:  # noqa: BLE001 - deliberate broad catch per dataset
            cached = load_cached(outdir, name)
            if cached is not None:
                cached["stale"] = True
                cached["last_fetch_error"] = str(err)[:300]
                save(outdir, name, cached)
                print(f"  ⚠ {name}: fetch failed ({err}); serving stale cache", flush=True)
                produced.append(name)
            else:
                print(f"  ✗ {name}: fetch failed and no cache exists ({err})", flush=True)
                failures.append(name)

    manifest = {
        "updated_at": now_iso(),
        "fresh": sorted(n for n in FETCHERS if n in produced and n not in failures),
        "stale": sorted(set(produced) - set(FETCHERS.keys()) | set()),
        "failed_no_cache": failures,
    }
    # rebuild stale list accurately from files
    stale = []
    for name in FETCHERS:
        cached = load_cached(outdir, name)
        if cached and cached.get("stale"):
            stale.append(name)
    manifest["stale"] = sorted(stale)
    manifest["fresh"] = sorted(n for n in FETCHERS if n not in stale and n not in failures)
    save(outdir, "_manifest", manifest)

    print(f"\nDone: {len(produced)}/4 datasets available "
          f"(fresh={manifest['fresh']}, stale={manifest['stale']}, missing={failures})",
          flush=True)
    # Fail hard only if we could not produce anything usable.
    return 1 if failures and len(produced) == 0 else 0


if __name__ == "__main__":
    sys.exit(main())
