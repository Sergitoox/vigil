<div align="center">

<img src="docs/assets/logo.svg" alt="vigil" width="100"/>

# vigil

**The world generates real-time intelligence. Most of it is invisible.**

`vigil` is an open-source, self-hosted MCP server that fuses live geospatial
data streams into a unified intelligence picture for any area of interest —
queryable by any AI agent in plain language.

**v0.1 ships fire intelligence via NASA FIRMS.** Maritime, conflict, weather,
and aerial domains are on the roadmap — see below.


[![License: MIT](https://img.shields.io/badge/license-MIT-%23D4D0C8?labelColor=%230D0D0D)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-%23E8E8E8?labelColor=%230D0D0D)](https://www.python.org/)
[![MCP Compatible](https://img.shields.io/badge/MCP-compatible-%234A2A7A?labelColor=%230D0D0D)](https://modelcontextprotocol.io/)


</div>

---

## The problem

Wildfires threaten infrastructure, ecosystems, and lives. NASA publishes
near-real-time fire detection data via satellite — free, public, and
updated multiple times a day. But it's raw CSV/JSON with no context layer.

No single place to ask: **what's the fire situation in this area, right now,
and how serious is it?**

AI agents that need to reason about real-world risk — for logistics,
insurance, emergency response, or general situational awareness — are
blind to this data unless someone builds the bridge.

`vigil` is that bridge.

---

## How it works

Define an area of interest. vigil queries NASA FIRMS for active fire
detections inside it, computes a risk assessment, and exposes the result
as an MCP server any agent can query.

```bash
git clone https://github.com/Sergitoox/vigil + cd vigil + uv sync
export VIGIL_FIRMS_KEY=your_free_nasa_key
vigil serve --aoi "-10,35,5,44"
```

Then ask your agent:

```
> What is the fire situation in Spain right now?

→ No active fires detected in the last 48 hours across the entire
  AOI. Risk level: NONE.
  
  Context: May–October is Spain's high-risk wildfire season, with
  peak activity typically in July–August.
```

---

## Data sources

| Domain | Source | Status |
|---|---|---|
| **Fire** | NASA FIRMS (VIIRS/MODIS) | ✅ **Live in v0.1** |
| Maritime | AISHub | 🔜 Roadmap (v0.2) |
| Conflict | ACLED | 🔜 Roadmap (v0.3) |
| Weather | NOAA GFS | 🔜 Roadmap (v0.4) |
| Aerial | OpenSky Network | 🔜 Roadmap (v0.5) |

All sources are free and public. See [Roadmap](#roadmap) for the full
multi-domain vision.

---

## MCP Tools — v0.1

| Tool | What it does |
|---|---|
| `get_active_fires` | All active fire detections in the AOI — coordinates, intensity (FRP), confidence, timestamp |
| `get_fire_summary` | Executive summary: detection counts, peak intensity, risk level, recommendations |
| `assess_fire_risk` | Structured risk assessment with explicit risk factors, for operational decisions |

---

## Quickstart

```bash
pip install vigil-mcp
```

Get a free NASA FIRMS API key (takes under a minute):
**https://firms.modaps.eosdis.nasa.gov/api/map_key/**

```bash
export VIGIL_FIRMS_KEY=your_key

vigil serve --aoi "-10,35,5,44"
# bbox format: west,south,east,north
# or a WKT polygon: "POLYGON((-10 35, 5 35, 5 44, -10 44, -10 35))"
```

Add to your Claude Desktop config
(`~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "vigil": {
      "command": "/path/to/uv",
      "args": ["run", "--directory", "/path/to/vigil", "vigil", "serve", "--aoi", "-10,35,5,44"],
      "env": { "VIGIL_FIRMS_KEY": "your_key" }
    }
  }
}
```

---

## Architecture

```
NASA FIRMS API
      │
      ▼  httpx async, on-demand fetch
FIRMSIngestor
      │  normalizes → FireDetection (Pydantic)
      ▼
DuckDB (spatial extension)
      │  AOI-filtered, deduplicated storage
      ▼
Tool layer (get_active_fires / get_fire_summary / assess_fire_risk)
      │
      ▼
MCP Server (stdio) ──► Claude Desktop / any MCP-compatible agent
```

vigil runs entirely in-process. No external database server, no Spark,
no cloud dependency. 

The ingestor abstraction (`BaseIngestor`) is designed so that adding a
new domain — maritime, conflict, weather — means writing one new file,
not restructuring the project. v0.1 is the reference implementation of
that pattern, not a one-off script.

---

## Roadmap

### v0.1 — Fire intelligence ✅ *shipped*
- [x] NASA FIRMS ingestion
- [x] DuckDB geospatial storage with AOI filtering
- [x] `get_active_fires`, `get_fire_summary`, `assess_fire_risk`
- [x] MCP server, tested end-to-end with Claude Desktop

### v0.2 — Maritime domain
- [ ] AISHub ingestion — live vessel positions
- [ ] `get_vessels_in_aoi`, `get_vessel_history`
- [ ] Route deviation detection

### v0.3 — Cross-domain fusion
- [ ] ACLED conflict event ingestion
- [ ] `get_cross_domain_correlations` — the first genuinely differentiated
      capability: detecting spatiotemporal correlations between fire,
      maritime, and conflict activity in the same AOI

### v0.4 — Weather context
- [ ] NOAA GFS ingestion — wind, visibility, precipitation
- [ ] Fire spread direction estimation using wind data

### v0.5 — Full picture → v1.0
- [ ] OpenSky aerial ingestion
- [ ] `get_full_intelligence_picture` — synthesized multi-domain briefing


---

## Contributing

vigil is early-stage. If you work in emergency response, insurance,
logistics, or environmental monitoring and have opinions on what real
fire intelligence should look like — open an issue.

```bash
git clone https://github.com/Sergitoox/vigil
cd vigil
uv sync --extra dev
uv run pytest
```

See [CONTRIBUTING.md](CONTRIBUTING.md).

---

<div align="center">

Built by Sergio· Senior Data Engineer · Madrid

[⭐ Star on GitHub](https://github.com/Sergitoox/vigil) 
</div>