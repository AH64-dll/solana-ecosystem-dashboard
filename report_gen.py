#!/usr/bin/env python3
"""Render REPORT.md and data/summary.json from the cached JSON in data/.

Reads only local cache files produced by fetch_data.py (no network).
Gracefully degrades: any missing dataset is skipped with a note.

Usage: python3 report_gen.py [--datadir data]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

D = 1_000_000_000
M = 1_000_000


def fmt_usd(v, prec=2):
    if v is None:
        return "n/a"
    sign = "-" if v < 0 else ""
    v = abs(v)
    if v >= D:
        return f"{sign}${v / D:.{prec}f}B"
    if v >= M:
        return f"{sign}${v / M:.1f}M"
    return f"{sign}${v:,.0f}"


def fmt_pct(v):
    return "n/a" if v is None else f"{v:+.1f}%"


def ts_to_date(ts):
    return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%d")


def load(datadir: Path, name: str):
    path = datadir / f"{name}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as err:
        print(f"  ! could not parse {path}: {err}", file=sys.stderr)
        return None


def value_at(points, days_ago, now_ts=None):
    """Nearest point at least `days_ago` days before the last point."""
    if not points:
        return None
    last_ts = now_ts or points[-1][0]
    target = last_ts - days_ago * 86400
    best = None
    for ts, val in points:
        if ts <= target:
            best = val
        else:
            break
    return best


def pct_change(now_v, then_v):
    if not now_v or not then_v or then_v == 0:
        return None
    return (now_v - then_v) / then_v * 100.0


def trend_block(points, label, current):
    lines = []
    for days in (30, 90, 365):
        past = value_at(points, days)
        chg = pct_change(current, past)
        past_s = fmt_usd(past)
        chg_s = fmt_pct(chg)
        arrow = "📈" if (chg or 0) > 0 else ("📉" if (chg or 0) < 0 else "➖")
        lines.append(f"- **{days}d:** {past_s} → {fmt_usd(current)} ({chg_s}) {arrow}")
    ath = max((v for _, v in points), default=None)
    ath_date = next((ts_to_date(ts) for ts, v in points if v == ath), None)
    from_ath = pct_change(current, ath)
    lines.append(f"- **All-time high:** {fmt_usd(ath)} on {ath_date} "
                 f"(now {fmt_pct(from_ath)} from ATH)")
    return "\n".join(lines), {"days": {"30": pct_change(current, value_at(points, 30)),
                                       "90": pct_change(current, value_at(points, 90)),
                                       "365": pct_change(current, value_at(points, 365))},
                              "ath": ath, "from_ath_pct": from_ath}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--datadir", default="data")
    args = ap.parse_args()
    datadir = Path(args.datadir)

    tvl = load(datadir, "tvl_history")
    stables = load(datadir, "stablecoins")
    market = load(datadir, "market")
    protocols = load(datadir, "protocols")

    if not any((tvl, stables, market, protocols)):
        print("No cached datasets found in ./data — run fetch_data.py first.", file=sys.stderr)
        return 1

    updated = ""
    manifest = load(datadir, "_manifest") or {}
    if manifest.get("updated_at"):
        updated = f"Data refreshed **{manifest['updated_at']}** · "
    stale_note = ""
    if manifest.get("stale"):
        stale_note = f"\n\n> ⚠️ Stale cache served for: {', '.join(manifest['stale'])} (last refresh failed).\n"

    summary = {"generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
               "stale_datasets": manifest.get("stale", [])}

    # ---------------- TVL ----------------
    tvl_lines, tvl_stats = "", {}
    tvl_now = tvl_rank = None
    if tvl and tvl.get("points"):
        pts = tvl["points"]
        tvl_now = tvl.get("current_tvl") or pts[-1][1]
        tvl_rank = tvl.get("chain_rank")
        block, tvl_stats = trend_block(pts, "TVL", tvl_now)
        tvl_lines = block
        summary["tvl"] = {"current": tvl_now, "rank": tvl_rank,
                          "change_pct": tvl_stats["days"], "ath": tvl_stats["ath"]}
    else:
        tvl_lines = "- n/a (fetch failed)"

    # ---------------- Stablecoins ----------------
    st_lines, st_stats = "", {}
    st_now = None
    if stables and stables.get("points"):
        spts = stables["points"]
        st_now = stables.get("current") or spts[-1][1]
        block, st_stats = trend_block(spts, "Stablecoins", st_now)
        st_lines = block
        summary["stablecoins"] = {"current": st_now,
                                  "change_pct": st_stats["days"],
                                  "ath": st_stats["ath"]}
    else:
        st_lines = "- n/a (fetch failed)"

    # ---------------- Market ----------------
    mkt_lines = ""
    sol_price = None
    if market:
        p = market.get("current_price")
        sol_price = p
        mkt_lines = "\n".join([
            f"| SOL price | {'$' + format(p, ',.2f') if p is not None else 'n/a'} |",
            f"| 24h | {fmt_pct(market.get('price_change_percentage_24h_in_currency'))} |",
            f"| 7d | {fmt_pct(market.get('price_change_percentage_7d_in_currency'))} |",
            f"| 30d | {fmt_pct(market.get('price_change_percentage_30d_in_currency'))} |",
            f"| 1y | {fmt_pct(market.get('price_change_percentage_1y_in_currency'))} |",
            f"| Market cap | {fmt_usd(market.get('market_cap'))} |",
            f"| 24h volume | {fmt_usd(market.get('total_volume'))} |",
            f"| Circulating supply | {market.get('circulating_supply'):,.0f} SOL |"
            if market.get("circulating_supply") else "| Circulating supply | n/a |",
            f"| ATH | ${market.get('ath'):,.2f} ({fmt_pct(market.get('ath_change_percentage'))} from ATH) |"
            if market.get("ath") else "| ATH | n/a |",
        ])
        summary["sol"] = {"price": market.get("current_price"),
                          "market_cap": market.get("market_cap"),
                          "change_pct": {
                              "24h": market.get("price_change_percentage_24h_in_currency"),
                              "7d": market.get("price_change_percentage_7d_in_currency"),
                              "30d": market.get("price_change_percentage_30d_in_currency"),
                              "1y": market.get("price_change_percentage_1y_in_currency")}}
    else:
        mkt_lines = "| SOL market data | n/a (fetch failed) |"

    # ---------------- Protocols ----------------
    proto_table = ""
    movers_rows = []
    top10 = []
    if protocols and protocols.get("top"):
        rows = protocols["top"]
        top10 = rows[:10]
        proto_table = "\n".join(
            f"| {i} | [{r['name']}]({r.get('url') or '#'}) | {r.get('category') or '—'} | "
            f"{fmt_usd(r['tvl_solana'])} | {fmt_pct(r.get('change_1d'))} | {fmt_pct(r.get('change_7d'))} |"
            for i, r in enumerate(top10, 1))
        # notable movers among all tracked protocols (min $50M Solana TVL to avoid noise)
        eligible = [r for r in rows if r["tvl_solana"] >= 50 * M]
        gainers = sorted((r for r in eligible if r.get("change_7d") is not None),
                         key=lambda r: r["change_7d"], reverse=True)[:5]
        losers = sorted((r for r in eligible if r.get("change_7d") is not None),
                        key=lambda r: r["change_7d"])[:5]
        for title, group in (("Top 7-day gainers", gainers), ("Top 7-day losers", losers)):
            movers_rows.append(f"**{title}**\n")
            movers_rows.extend(
                f"- **{r['name']}** ({r.get('category') or '—'}): {fmt_usd(r['tvl_solana'])}, "
                f"7d {fmt_pct(r['change_7d'])}" for r in group)
            movers_rows.append("")
        summary["protocols"] = {
            "count_on_solana": protocols.get("protocol_count_on_solana"),
            "top10_names": [r["name"] for r in top10],
            "top_gainers_7d": [{"name": r["name"], "change_7d": r["change_7d"]} for r in gainers],
            "top_losers_7d": [{"name": r["name"], "change_7d": r["change_7d"]} for r in losers]}
    else:
        proto_table = "| – | protocol data unavailable | – | – | – | – |"
        movers_rows = ["n/a (fetch failed)\n"]

    # ---------------- Headline ----------------
    headline_bits = []
    if tvl_now is not None:
        rank_s = f", #{tvl_rank} chain by TVL" if tvl_rank else ""
        headline_bits.append(f"Solana DeFi TVL stands at **{fmt_usd(tvl_now)}**{rank_s}")
    if st_now is not None:
        headline_bits.append(f"with **{fmt_usd(st_now)}** in stablecoins circulating")
    if sol_price is not None:
        d30 = (market or {}).get("price_change_percentage_30d_in_currency")
        headline_bits.append(f"SOL trading at **${sol_price:,.2f}" +
                             (f" ({d30:+.1f}% / 30d)**" if d30 is not None else "**"))
    headline = " · ".join(headline_bits) if headline_bits else "No data available."

    report = f"""# Solana Ecosystem Report

{updated}auto-generated by [`report_gen.py`](report_gen.py) from DefiLlama & CoinGecko data.{stale_note}

## TL;DR

> {headline}

## Total Value Locked

**Current TVL: {fmt_usd(tvl_now)}**{f" (rank #{tvl_rank} among all chains)" if tvl_rank else ""}

{tvl_lines}

## Stablecoins on Solana

**Current circulating stablecoins: {fmt_usd(st_now)}**

{st_lines}

## SOL Market Snapshot

| Metric | Value |
|---|---|
{mkt_lines}

## Top 10 Protocols on Solana (by Solana-side TVL)

| # | Protocol | Category | Solana TVL | 1d | 7d |
|---|---|---|---|---|---|
{proto_table}

*Of {protocols.get('protocol_count_on_solana', '?') if protocols else '?'} protocols tracked on Solana; table shows the ten largest by Solana-side TVL.*

## Notable Movers (7d)

{chr(10).join(movers_rows).strip()}

---

### Methodology

- **TVL:** DefiLlama `historicalChainTvl/Solana` — sum of USD value of assets in on-chain DeFi apps.
- **Stablecoins:** DefiLlama stablecoin charts for Solana (`peggedUSD` circulation).
- **Protocols:** DefiLlama protocol registry filtered to `chainTvls.Solana`; CEX treasuries appear because DefiLlama tracks them as venues.
- **Market data:** CoinGecko `/coins/markets`.
- Trend percentages compare the latest point against the nearest point ≥ N days back.

### Files

- `data/tvl_history.json`, `data/stablecoins.json`, `data/market.json`, `data/protocols.json`, `data/_manifest.json`
- Dashboard: [`index.html`](index.html)

*Report generated {summary['generated_at']}. Not financial advice.*
"""
    Path("REPORT.md").write_text(report, encoding="utf-8")
    (datadir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"✓ wrote REPORT.md ({len(report) / 1024:.1f} KB) and data/summary.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
