# Solana Ecosystem Dashboard

An auto-updating, single-file interactive dashboard tracking the Solana ecosystem:
DeFi TVL (full history), stablecoin circulating supply, top protocols by TVL,
7-day gainers, and SOL market stats — all pulled from free public APIs.

**Entry for the Superteam Earn bounty: "Develop Solana Ecosystem Auto-Updating Report & Interactive Dashboard" ($1,000 USDC).**

![stack](https://img.shields.io/badge/stack-Python%20%2B%20ECharts-14f195) ![deps](https://img.shields.io/badge/runtime%20deps-zero-9945ff)

## What it shows

| Panel | Source | Notes |
|---|---|---|
| DeFi TVL history (line) | `api.llama.fi/v2/historicalChainTvl/Solana` | 1,900+ daily points |
| Stablecoin supply (area) | `stablecoins.llama.fi/stablecoincharts/Solana` | 1,500+ daily points |
| Top protocols by TVL (bar) | `api.llama.fi/protocols` filtered to Solana | CEX entries excluded — DeFi focus |
| Stat cards | summary of the above + CoinGecko | TVL / rank / stables / SOL price / protocol count |
| 7d gainers table | derived from protocol changes | top 5 movers |

Latest snapshot embedded in this repo: **TVL $5.38B (#3 chain), $16.45B stablecoins (+3.7%/30d), SOL $90.23 (+16.4%/30d), 436 protocols.**

## Architecture

```
fetch_data.py ──▶ data/*.json ──▶ report_gen.py ──▶ REPORT.md
      │                                   │
      └──▶ build_dashboard.py ◀───────────┘
                 │
                 ▼
           index.html  (single file: data + vendor/echarts.min.js)
                 ▲
        .github/workflows/update.yml (daily cron: fetch → report → rebuild → commit)
```

- **Zero runtime dependencies** — plain `urllib` with caching, stale-fallback, and graceful degradation per source.
- **Single-file output** — `index.html` embeds the data JSON; host it anywhere (GitHub Pages, S3, IPFS).
- **Auto-updating** — GitHub Action re-runs the pipeline daily and commits refreshed artifacts.

## Run locally

```bash
python3 fetch_data.py        # pulls fresh data into data/
python3 report_gen.py        # renders REPORT.md
python3 build_dashboard.py   # rebuilds index.html with embedded data
# open index.html in a browser
```

## Deploy your own copy

1. Fork this repo.
2. Settings → Actions → enable workflows.
3. (Optional) Settings → Pages → deploy from branch → `/root`.
The daily workflow keeps both the report and the dashboard current automatically.

## Design decisions

- **Dark theme + Solana brand colors** (`#14f195` / `#9945FF`) for readability and identity.
- **ECharts over heavier frameworks**: one vendored JS file, no build step, instant load.
- **Data embedded at build time**, not fetched client-side: the page works offline, loads instantly, and never hits API rate limits from visitors.
- **Stale-tolerant pipeline**: if an API is down, the previous cache is kept and flagged (`stale_datasets` in `data/_manifest.json`) instead of breaking the build.

## License

MIT
