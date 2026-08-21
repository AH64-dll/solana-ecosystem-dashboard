#!/usr/bin/env python3
"""Build index.html: dark single-file ECharts dashboard with embedded live data."""
import json, pathlib

root = pathlib.Path(__file__).parent
summary = json.load(open(root / "data/summary.json"))
tvl = json.load(open(root / "data/tvl_history.json"))
st = json.load(open(root / "data/stablecoins.json"))
protos = json.load(open(root / "data/protocols.json"))

def series(points, max_pts=800):
    pts = points[-max_pts:]
    return [[p[0] * 1000, round(p[1], 2)] for p in pts]

tvl_series = series(tvl["points"])
st_series = series(st["points"])
raw_top = protos.get("top", [])[:10]
# exclude CEX entries for a DeFi-focused chart
defi_top = [p for p in raw_top if p.get("category", "").upper() != "CEX"] or raw_top
proto_names = [p.get("name", "?") for p in defi_top]
proto_tvl = [round(p.get("tvl_solana", 0) / 1e9, 3) for p in defi_top]

gainers = summary["protocols"].get("top_gainers_7d", [])[:5]

html = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Solana Ecosystem Dashboard</title>
<script src="vendor/echarts.min.js"></script>
<style>
  :root { --bg:#0b0e14; --card:#131722; --border:#1f2735; --text:#dbe4f0; --muted:#8b98ab; --accent:#14f195; --accent2:#9945ff; }
  * { box-sizing:border-box; margin:0; padding:0; }
  body { background:var(--bg); color:var(--text); font-family:'Segoe UI',system-ui,sans-serif; padding:24px; }
  h1 { font-size:22px; font-weight:600; letter-spacing:.3px; }
  h1 span { color:var(--accent); }
  .sub { color:var(--muted); font-size:12.5px; margin-top:4px; }
  .grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(210px,1fr)); gap:14px; margin:20px 0; }
  .card { background:var(--card); border:1px solid var(--border); border-radius:12px; padding:16px; }
  .stat .label { color:var(--muted); font-size:11.5px; text-transform:uppercase; letter-spacing:.8px; }
  .stat .value { font-size:26px; font-weight:700; margin-top:6px; }
  .stat .delta { font-size:13px; margin-top:4px; }
  .up { color:var(--accent); } .down { color:#ff6b81; }
  .charts { display:grid; grid-template-columns:1fr 1fr; gap:14px; }
  @media(max-width:900px){ .charts{grid-template-columns:1fr;} }
  .chart-card h2 { font-size:14px; color:var(--muted); font-weight:500; margin-bottom:8px; }
  .chart { width:100%; height:320px; }
  table { width:100%; border-collapse:collapse; font-size:13px; }
  th,td { text-align:left; padding:8px 10px; border-bottom:1px solid var(--border); }
  th { color:var(--muted); font-weight:500; text-transform:uppercase; font-size:11px; letter-spacing:.6px; }
  footer { color:var(--muted); font-size:11.5px; margin-top:18px; }
  a { color:var(--accent); text-decoration:none; }
</style>
</head>
<body>
<h1>SOLANA <span>ECOSYSTEM</span> DASHBOARD</h1>
<div class="sub">Auto-updating report · generated __GENERATED__ · data: DefiLlama + CoinGecko public APIs</div>

<div class="grid">
  <div class="card stat"><div class="label">DeFi TVL</div><div class="value">$__TVL__B</div><div class="delta __TVLCLS__">30d: __TVL30__%</div></div>
  <div class="card stat"><div class="label">Chain Rank</div><div class="value">#__RANK__</div><div class="delta" style="color:var(--muted)">by total TVL</div></div>
  <div class="card stat"><div class="label">Stablecoins</div><div class="value">$__ST__B</div><div class="delta __STCLS__">30d: __ST30__%</div></div>
  <div class="card stat"><div class="label">SOL Price</div><div class="value">$__SOL__</div><div class="delta __SOLCLS__">30d: __SOL30__%</div></div>
  <div class="card stat"><div class="label">Protocols</div><div class="value">__NPROT__</div><div class="delta" style="color:var(--muted)">deployed on Solana</div></div>
</div>

<div class="charts">
  <div class="card chart-card"><h2>Total Value Locked — full history</h2><div id="tvl" class="chart"></div></div>
  <div class="card chart-card"><h2>Stablecoin Circulating Supply</h2><div id="st" class="chart"></div></div>
  <div class="card chart-card"><h2>Top Protocols by TVL ($B)</h2><div id="protos" class="chart"></div></div>
  <div class="card chart-card"><h2>Top TVL Gainers (7d)</h2><table>
    <tr><th>Protocol</th><th>7d change</th></tr>
    __GAINROWS__
  </table></div>
</div>

<footer>Built for the Superteam Earn bounty · pipeline: fetch_data.py → report_gen.py → this page · refresh daily via GitHub Actions · <a href="REPORT.md">read the full report</a></footer>

<script>
const tvlPts = __TVLSERIES__;
const stPts = __STSERIES__;
const dark = { textStyle:{color:'#dbe4f0'}, backgroundColor:'transparent' };
function base(opt){ return Object.assign({}, dark, opt); }
function fmt(ts){ return new Date(ts).toLocaleDateString('en-US',{month:'short',year:'2-digit'}); }

const tvlChart = echarts.init(document.getElementById('tvl'));
tvlChart.setOption(base({
  xAxis:{type:'time', axisLabel:{formatter:p=>fmt(p.value)}, splitLine:{show:false}},
  yAxis:{type:'value', name:'$B', scale:true, splitLine:{lineStyle:{color:'#1f2735'}},
         axisLabel:{formatter:v=>'$'+(v/1e9).toFixed(0)+'B'}},
  tooltip:{trigger:'axis', valueFormatter:v=>'$'+(v/1e9).toFixed(2)+'B'},
  series:[{type:'line', data:tvlPts, showSymbol:false, smooth:true,
    lineStyle:{color:'#14f195',width:2},
    areaStyle:{color:{type:'linear',x:0,y:0,x2:0,y2:1,colorStops:[
      {offset:0,color:'rgba(20,241,149,.25)'},{offset:1,color:'rgba(20,241,149,0)'}]}}}]
}));

const stChart = echarts.init(document.getElementById('st'));
stChart.setOption(base({
  xAxis:{type:'time', axisLabel:{formatter:p=>fmt(p.value)}, splitLine:{show:false}},
  yAxis:{type:'value', scale:true, splitLine:{lineStyle:{color:'#1f2735'}},
         axisLabel:{formatter:v=>'$'+(v/1e9).toFixed(0)+'B'}},
  tooltip:{trigger:'axis', valueFormatter:v=>'$'+(v/1e9).toFixed(2)+'B'},
  series:[{type:'line', data:stPts, showSymbol:false, smooth:true,
    lineStyle:{color:'#9945ff',width:2},
    areaStyle:{color:{type:'linear',x:0,y:0,x2:0,y2:1,colorStops:[
      {offset:0,color:'rgba(153,69,255,.25)'},{offset:1,color:'rgba(153,69,255,0)'}]}}}]
}));

const pChart = echarts.init(document.getElementById('protos'));
pChart.setOption(base({
  xAxis:{type:'value', splitLine:{lineStyle:{color:'#1f2735'}}, axisLabel:{formatter:v=>'$'+v+'B'}},
  yAxis:{type:'category', data:[...__PNAMES__].reverse(), axisLabel:{fontSize:11}},
  tooltip:{trigger:'axis', valueFormatter:v=>'$'+v+'B'},
  series:[{type:'bar', data:[...__PVALS__].reverse(), barWidth:'55%',
    itemStyle:{color:{type:'linear',x:0,y:0,x2:1,y2:0,colorStops:[
      {offset:0,color:'#9945ff'},{offset:1,color:'#14f195'}]}, borderRadius:4}}]
}));

window.addEventListener('resize', ()=>{tvlChart.resize();stChart.resize();pChart.resize();});
</script>
</body>
</html>"""

def delta_cls(v):
    return "up" if v >= 0 else "down"

gain_rows = "\n".join(
    f'<tr><td>{g["name"]}</td><td class="{"up" if g["change_7d"]>=0 else "down"}">{g["change_7d"]:+.1f}%</td></tr>'
    for g in gainers
) or '<tr><td colspan="2" style="color:var(--muted)">no data</td></tr>'

html = (html
    .replace("__GENERATED__", summary.get("generated_at", ""))
    .replace("__TVL__", f'{summary["tvl"]["current"]/1e9:.2f}')
    .replace("__TVL30__", f'{summary["tvl"]["change_pct"]["30"]:+.1f}')
    .replace("__TVLCLS__", delta_cls(summary["tvl"]["change_pct"]["30"]))
    .replace("__RANK__", str(summary["tvl"]["rank"]))
    .replace("__ST__", f'{summary["stablecoins"]["current"]/1e9:.2f}')
    .replace("__ST30__", f'{summary["stablecoins"]["change_pct"]["30"]:+.1f}')
    .replace("__STCLS__", delta_cls(summary["stablecoins"]["change_pct"]["30"]))
    .replace("__SOL__", f'{summary["sol"]["price"]:.2f}')
    .replace("__SOL30__", f'{summary["sol"]["change_pct"]["30d"]:+.1f}')
    .replace("__SOLCLS__", delta_cls(summary["sol"]["change_pct"]["30d"]))
    .replace("__NPROT__", str(summary["protocols"]["count_on_solana"]))
    .replace("__GAINROWS__", gain_rows)
    .replace("__TVLSERIES__", json.dumps(tvl_series))
    .replace("__STSERIES__", json.dumps(st_series))
    .replace("__PNAMES__", json.dumps(proto_names))
    .replace("__PVALS__", json.dumps(proto_tvl))
)

out = root / "index.html"
out.write_text(html)
print(f"wrote {out} ({len(html)//1024} KB), tvl pts={len(tvl_series)}, st pts={len(st_series)}")
