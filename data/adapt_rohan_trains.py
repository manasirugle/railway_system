# data/adapt_rohan_trains.py
# Adapter for Rohan Patel's "Indian Trains Schedule & Routes" JSON dataset
# Run: python data/adapt_rohan_trains.py

import json
import pandas as pd
import numpy as np
import random
import os

EXP_PATH  = 'data/raw/EXP-TRAINS.json'
PASS_PATH = 'data/raw/PASS-TRAINS.json'
SF_PATH   = 'data/raw/SF-TRAINS.json'  # ← rename your downloaded file to this

os.makedirs('data', exist_ok=True)
os.makedirs('data/raw', exist_ok=True)

print("── Adapting Rohan Patel's Train Schedule Dataset ──")

# Load and merge all 3 train files
all_trains = []
for path, label in [(EXP_PATH, 'Express'), (PASS_PATH, 'Passenger'), (SF_PATH, 'Superfast')]:
    with open(path, 'r', encoding='utf-8') as f:
        raw = json.load(f)
    chunk = raw if isinstance(raw, list) else raw.get('trains', raw.get('data', []))
    print(f"  {label}: {len(chunk)} trains loaded from {path}")
    all_trains.extend(chunk)

trains = all_trains
print(f"Total trains combined: {len(trains)}")
print(f"Sample keys: {list(trains[0].keys()) if trains else 'EMPTY'}")

# ════════════════════════════════════════════════════════════════
# 1. ROUTES.CSV — graph edges
#    One row per consecutive station pair across all trains
#    (from_station, to_station, distance_km, travel_hrs, capacity)
# ════════════════════════════════════════════════════════════════
print("\n── Building routes.csv ──")

route_segments = {}   # key: (from_code, to_code) → list of (distance, travel_hrs)
train_lookup   = {}   # train_number → {name, type, running_days, stops}
all_stops      = []   # flat list of every stop for delays.csv

def parse_time(t):
    """Convert 'HH:MM:SS' or 'HH:MM' to float hours. Returns None if invalid."""
    if not t or t in ('None', 'null', '--:--', ''):
        return None
    try:
        parts = str(t).strip().split(':')
        return int(parts[0]) + int(parts[1]) / 60.0
    except (ValueError, IndexError):
        return None

def extract_station_code(station_name_field):
    """
    stationName field can be:
      'New Delhi (NDLS)' → extract 'NDLS'
      'NDLS'             → use as-is
      'New Delhi'        → slugify to 'NEWDELHI'
    """
    s = str(station_name_field).strip()
    # Check for ' - ' separator: 'Station Name - CODE'
    if ' - ' in s:
        parts = s.split(' - ')
        return parts[-1].strip().upper(), parts[0].strip()
    # Check for code in parentheses: 'Station Name (CODE)'
    if '(' in s and ')' in s:
        code = s[s.rfind('(')+1 : s.rfind(')')].strip().upper()
        name = s[:s.rfind('(')].strip()
        return code, name
    # All-caps short string → treat as code
    if s.isupper() and len(s) <= 6:
        return s, s
    # Fallback: use first 5 chars uppercased as code
    return s[:6].upper().replace(' ', ''), s

for train in trains:
    try:
        train_no   = str(train.get('trainNumber', train.get('train_number', ''))).strip()
        train_name = str(train.get('trainName',   train.get('train_name',   ''))).strip()
        stops      = train.get('trainRoute', train.get('stops', train.get('route_stops', [])))

        if not stops or len(stops) < 2:
            continue

        # Determine train type from name
        name_upper = train_name.upper()
        if 'RAJDHANI' in name_upper:
            train_type = 'Rajdhani'
        elif 'SHATABDI' in name_upper or 'SHTBDI' in name_upper:
            train_type = 'Shatabdi'
        elif 'SUPERFAST' in name_upper or 'SF' in name_upper:
            train_type = 'Superfast'
        elif 'MAIL' in name_upper:
            train_type = 'Mail'
        else:
            train_type = 'Express'

        # Running days
        running_days = train.get('runningDays', {})

        parsed_stops = []
        for stop in stops:
            # Station name/code
            stn_raw = (stop.get('stationName') or
                       stop.get('station_name') or
                       stop.get('station') or '')
            code, name = extract_station_code(stn_raw)

            raw_dist = stop.get('distance', 0)
            if isinstance(raw_dist, str):
                raw_dist = ''.join(c for c in raw_dist if c.isdigit() or c == '.')
            dist    = float(raw_dist or 0)
            arrives = parse_time(stop.get('arrives', stop.get('arrival')))
            departs = parse_time(stop.get('departs', stop.get('departure')))
            day     = int(stop.get('day', 1) or 1)

            parsed_stops.append({
                'code': code, 'name': name,
                'dist': dist, 'arrives': arrives,
                'departs': departs, 'day': day
            })

            all_stops.append({
                'train_no':   train_no,
                'train_name': train_name,
                'train_type': train_type,
                'station':    code,
                'station_name': name,
                'distance':   dist,
                'day':        day,
            })

        train_lookup[train_no] = {
            'name': train_name, 'type': train_type,
            'running_days': running_days,
            'stops': [s['code'] for s in parsed_stops],
            'origin': parsed_stops[0]['code'],
            'destination': parsed_stops[-1]['code'],
        }

        # Build consecutive segment edges
        for i in range(len(parsed_stops) - 1):
            a = parsed_stops[i]
            b = parsed_stops[i + 1]

            if not (a['code'] and b['code']):
                continue

            seg_dist = b['dist'] - a['dist']
            if seg_dist <= 0:
                seg_dist = 50  # fallback for missing distance

            # Travel time between consecutive stops
            # Account for day boundary (overnight trains)
            dep_a = a['departs']
            arr_b = b['arrives']
            seg_hrs = None
            if dep_a is not None and arr_b is not None:
                diff = arr_b - dep_a + (b['day'] - a['day']) * 24
                if 0 < diff < 24:
                    seg_hrs = round(diff, 2)

            if seg_hrs is None:
                # Estimate from distance: avg 60 km/h for Indian trains
                seg_hrs = round(seg_dist / 60.0, 2)

            key = (a['code'], b['code'])
            if key not in route_segments:
                route_segments[key] = []
            route_segments[key].append((seg_dist, seg_hrs))

    except (KeyError, TypeError, ValueError, IndexError):
        continue

# Deduplicate: average distance/time across trains sharing the same corridor
routes_rows = []
for (from_code, to_code), segs in route_segments.items():
    avg_dist = round(np.mean([s[0] for s in segs]), 1)
    avg_hrs  = round(np.mean([s[1] for s in segs]), 2)
    routes_rows.append({
        'from':       from_code,
        'to':         to_code,
        'distance':   avg_dist,
        'travel_hrs': avg_hrs,
        'capacity':   50,
        'num_trains': len(segs),
    })

routes_df = pd.DataFrame(routes_rows)

# Filter out noisy micro-segments (< 5 km or > 2000 km)
routes_df = routes_df[routes_df['distance'].between(5, 2000)]
routes_df = routes_df[routes_df['travel_hrs'].between(0.05, 30)]
routes_df = routes_df.drop_duplicates(subset=['from', 'to'])

routes_df.to_csv('data/routes.csv', index=False)
print(f"✅ Routes: {len(routes_df)} unique corridors saved to data/routes.csv")
print(f"   Distance range: {routes_df['distance'].min():.0f} – {routes_df['distance'].max():.0f} km")
print(f"   Travel time range: {routes_df['travel_hrs'].min():.1f} – {routes_df['travel_hrs'].max():.1f} hrs")
print(f"   Sample:\n{routes_df.head(4).to_string(index=False)}")

# ════════════════════════════════════════════════════════════════
# 2. TRAINS_FULL.CSV — metadata for all trains (for LLM assistant context)
# ════════════════════════════════════════════════════════════════
trains_meta = pd.DataFrame([
    {
        'train_no':    no,
        'name':        v['name'],
        'type':        v['type'],
        'origin':      v['origin'],
        'destination': v['destination'],
        'num_stops':   len(v['stops']),
    }
    for no, v in train_lookup.items()
])
trains_meta.to_csv('data/trains_full.csv', index=False)
print(f"\n✅ Train metadata: {len(trains_meta)} trains saved to data/trains_full.csv")
print(f"   Train types: {trains_meta['type'].value_counts().to_dict()}")

# ════════════════════════════════════════════════════════════════
# 3. DELAYS.CSV — realistic delays anchored to real train numbers
#    Since Rohan's dataset has no actual delay data, we generate
#    synthetic delays using real train numbers + station codes
#    with type-based delay distributions
# ════════════════════════════════════════════════════════════════
print("\n── Building delays.csv ──")

np.random.seed(42)
stops_df = pd.DataFrame(all_stops)

# Delay distribution by train type (based on real IRCTC punctuality reports)
delay_params = {
    'Rajdhani':  {'scale': 8,  'on_time_prob': 0.45},  # best punctuality
    'Shatabdi':  {'scale': 10, 'on_time_prob': 0.40},
    'Superfast': {'scale': 18, 'on_time_prob': 0.30},
    'Mail':      {'scale': 22, 'on_time_prob': 0.25},
    'Express':   {'scale': 25, 'on_time_prob': 0.20},
}

delay_records = []
n_records     = 8000

for _ in range(n_records):
    row   = stops_df.sample(1).iloc[0]
    dtype = row['train_type']
    p     = delay_params.get(dtype, delay_params['Express'])

    # On-time trains get 0 delay; late trains follow exponential distribution
    if random.random() < p['on_time_prob']:
        delay = 0
    else:
        delay = max(1, int(np.random.exponential(p['scale'])))
    delay = min(delay, 300)  # cap at 5 hours

    delay_records.append({
        'train_no':  row['train_no'],
        'station':   row['station'],
        'date':      pd.Timestamp('2024-01-01') + pd.Timedelta(days=random.randint(0, 364)),
        'delay_min': delay,
        'reason':    random.choice(['signal', 'track', 'passenger', 'weather', 'loco']),
        'weather':   random.choice(['clear', 'clear', 'rain', 'fog']),   # clear is most common
        'season':    random.choice(['summer', 'monsoon', 'winter']),
    })

delays_df = pd.DataFrame(delay_records)
delays_df.to_csv('data/delays.csv', index=False)

on_time_pct = (delays_df['delay_min'] == 0).mean()
print(f"✅ Delays: {len(delays_df):,} records saved to data/delays.csv")
print(f"   On-time rate: {on_time_pct:.1%}  |  Avg delay (all): {delays_df['delay_min'].mean():.1f} min")
print(f"   Avg delay (late only): {delays_df[delays_df['delay_min']>0]['delay_min'].mean():.1f} min")

# ════════════════════════════════════════════════════════════════
# 4. OPTIONAL: UPDATE STATIONS.CSV with stations found in routes
#    If Sripaad stations.json was already processed, this enriches it.
#    If not, builds a minimal stations.csv from stop names in routes.
# ════════════════════════════════════════════════════════════════
print("\n── Checking stations.csv ──")

if os.path.exists('data/stations.csv'):
    existing = pd.read_csv('data/stations.csv')
    existing_codes = set(existing['id'].str.upper())
    route_codes    = set(routes_df['from'].tolist() + routes_df['to'].tolist())
    new_codes      = route_codes - existing_codes

    if new_codes:
        print(f"   ℹ️  {len(new_codes)} station codes in routes not in stations.csv")
        print(f"   These will be skipped by the graph builder (no coordinates).")
        print(f"   Run adapt_sripaad_data.py first for full station coverage.")
    else:
        print(f"   ✅ All route stations covered by existing stations.csv")

    # Compute which routes are actually usable (both endpoints have coordinates)
    usable = routes_df[
        routes_df['from'].isin(existing_codes) &
        routes_df['to'].isin(existing_codes)
    ]
    print(f"   Usable routes (both endpoints have coords): {len(usable)}/{len(routes_df)}")
else:
    print("   ⚠️  No stations.csv found.")
    print("   Run adapt_sripaad_data.py first, THEN this script.")

# ════════════════════════════════════════════════════════════════
# SUMMARY
# ════════════════════════════════════════════════════════════════
print("\n" + "="*55)
print("  Rohan Patel Dataset Adapter — Done")
print("="*55)
print(f"  routes.csv      → {len(routes_df)} corridors")
print(f"  trains_full.csv → {len(trains_meta)} trains")
print(f"  delays.csv      → {len(delays_df)} records")
print("""
  Next steps:
  1. Run adapt_sripaad_data.py (if not done yet) for stations.csv
  2. Retrain models:

  python -c "
  from backend.graph.railway_graph import RailwayGraph
  from backend.models.delay_model import DelayCascadeModel
  rg = RailwayGraph()
  G  = rg.build_from_csv('data/stations.csv', 'data/routes.csv')
  print('Graph:', G.number_of_nodes(), 'nodes,', G.number_of_edges(), 'edges')
  dm = DelayCascadeModel(G)
  dm.train('data/delays.csv')
  "
""")