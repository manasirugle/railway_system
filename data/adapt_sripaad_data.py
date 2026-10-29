# data/adapt_sripaad_data.py
# Custom adapter for Sripaad Srinivasan's Indian Railways GeoJSON dataset
# Run from your project root: python data/adapt_sripaad_data.py

import json
import pandas as pd
import numpy as np
import os
import random

# ── EDIT THESE PATHS to match your downloaded filenames ──────────
STATIONS_JSON  = 'data/raw/stations.json'
TRAINS_JSON    = 'data/raw/trains.json'
SCHEDULES_JSON = 'data/raw/schedules.json'
# ─────────────────────────────────────────────────────────────────

os.makedirs('data', exist_ok=True)
os.makedirs('data/raw', exist_ok=True)


# ════════════════════════════════════════════════════════════════
# 1. STATIONS  →  data/stations.csv
# GeoJSON FeatureCollection: coordinates=[lon, lat], properties={code, name, zone, state}
# ════════════════════════════════════════════════════════════════
def adapt_stations():
    print("\n── Adapting Stations ──")
    with open(STATIONS_JSON, 'r', encoding='utf-8') as f:
        geojson = json.load(f)

    features = geojson.get('features', geojson) if isinstance(geojson, dict) else geojson

    rows = []
    for feat in features:
        try:
            props = feat['properties']
            coords = feat['geometry']['coordinates']   # [lon, lat]
            rows.append({
                'id':       (props.get('code') or '').strip().upper(),
                'name':     (props.get('name') or '').strip(),
                'lon':      float(coords[0]),
                'lat':      float(coords[1]),
                'zone':     (props.get('zone') or 'NR').strip(),
                'state':    (props.get('state') or '').strip(),
                'capacity': 300,   # default — not in dataset
            })
        except (KeyError, TypeError, ValueError):
            continue

    df = pd.DataFrame(rows)

    # Clean: drop missing codes, filter to India bounding box
    df = df[df['id'].str.len() > 0]
    df = df[df['lat'].between(8.0, 37.5) & df['lon'].between(68.0, 97.5)]
    df = df.drop_duplicates(subset='id')

    # Assign realistic capacity by zone (larger zones = bigger stations)
    zone_capacity = {
        'NR': 500, 'CR': 480, 'WR': 460, 'SR': 440, 'ER': 430,
        'SER': 400, 'SCR': 390, 'NWR': 370, 'NCR': 380, 'NER': 300,
        'NFR': 280, 'ECR': 320, 'ECoR': 310, 'SWR': 340, 'WCR': 330,
    }
    df['capacity'] = df['zone'].map(zone_capacity).fillna(300).astype(int)

    # Save full set + a curated top-50 of major stations for the graph
    df.to_csv('data/stations_full.csv', index=False)

    # For the graph, prioritize stations that appear in schedules (loaded later)
    # For now save all — we'll filter after loading schedules
    df[['id','name','lat','lon','zone','capacity']].to_csv('data/stations.csv', index=False)

    print(f"✅ Stations: {len(df)} stations saved to data/stations.csv")
    print(f"   Sample: {df[['id','name','zone']].head(5).to_string(index=False)}")
    return df


# ════════════════════════════════════════════════════════════════
# 2. TRAINS + SCHEDULES  →  data/routes.csv + data/delays.csv
# Trains GeoJSON: properties={number, name, from_station_code, to_station_code, distance, duration_h, duration_m, type}
# Schedules array: {train_number, train_name, station_code, station_name, arrival, departure, day}
# ════════════════════════════════════════════════════════════════
def adapt_trains_and_routes():
    print("\n── Adapting Trains & Routes ──")
    with open(TRAINS_JSON, 'r', encoding='utf-8') as f:
        geojson = json.load(f)

    features = geojson.get('features', geojson) if isinstance(geojson, dict) else geojson

    train_rows = []
    route_pairs = set()   # (from, to) pairs for building graph edges

    for feat in features:
        try:
            p = feat['properties']
            train_no   = str(p.get('number', '')).strip()
            from_code  = str(p.get('from_station_code', '')).strip().upper()
            to_code    = str(p.get('to_station_code', '')).strip().upper()
            distance   = float(p.get('distance', 0))
            duration_h = float(p.get('duration_h', 0))
            duration_m = float(p.get('duration_m', 0))
            total_hrs  = duration_h + duration_m / 60.0
            train_type = str(p.get('type', 'Exp')).strip()

            if not (from_code and to_code and distance > 0):
                continue

            train_rows.append({
                'train_no':   train_no,
                'name':       str(p.get('name', '')).strip(),
                'from':       from_code,
                'to':         to_code,
                'distance':   distance,
                'total_hrs':  round(total_hrs, 2),
                'type':       train_type,
                'sleeper':    bool(p.get('sleeper', False)),
                'third_ac':   bool(p.get('third_ac', False)),
                'second_ac':  bool(p.get('second_ac', False)),
                'first_ac':   bool(p.get('first_ac', False)),
            })
            route_pairs.add((from_code, to_code, distance, total_hrs))

        except (KeyError, TypeError, ValueError):
            continue

    trains_df = pd.DataFrame(train_rows)
    trains_df.to_csv('data/trains_full.csv', index=False)
    print(f"✅ Trains: {len(trains_df)} trains parsed")

    # Build routes.csv (graph edges) from unique station pairs
    # Use average distance/time when multiple trains share a corridor
    route_df = trains_df.groupby(['from', 'to']).agg(
        distance=('distance', 'mean'),
        travel_hrs=('total_hrs', 'mean'),
    ).reset_index()
    route_df['distance']   = route_df['distance'].round(1)
    route_df['travel_hrs'] = route_df['travel_hrs'].round(2)
    route_df['capacity']   = 50   # default track capacity

    route_df.to_csv('data/routes.csv', index=False)
    print(f"✅ Routes: {len(route_df)} unique corridors saved to data/routes.csv")
    print(f"   Sample: {route_df.head(3).to_string(index=False)}")
    return trains_df, route_df


# ════════════════════════════════════════════════════════════════
# 3. SCHEDULES  →  filter stations.csv + build delays.csv
# ════════════════════════════════════════════════════════════════
def adapt_schedules_and_delays(stations_df, trains_df):
    print("\n── Adapting Schedules & Building Delays ──")
    with open(SCHEDULES_JSON, 'r', encoding='utf-8') as f:
        raw = json.load(f)

    # raw is a list of schedule objects
    schedules = raw if isinstance(raw, list) else raw.get('features', [])

    sched_df = pd.DataFrame(schedules)
    print(f"   Raw schedules: {len(sched_df)} stop records")
    print(f"   Columns: {list(sched_df.columns)}")

    # Standardise column names
    col_map = {
        'train_number': 'train_no', 'train_no': 'train_no',
        'station_code': 'station',  'station_code_': 'station',
        'station_name': 'station_name',
        'arrival':      'arrival',
        'departure':    'departure',
        'day':          'day',
    }
    sched_df = sched_df.rename(columns={k: v for k, v in col_map.items() if k in sched_df.columns})

    # ── Filter stations.csv to only keep stations that appear in schedules ──
    # This reduces graph complexity to stations with actual train traffic
    active_codes = set(sched_df['station'].dropna().str.upper().unique())
    stations_filtered = stations_df[stations_df['id'].isin(active_codes)].copy()

    if len(stations_filtered) < 10:
        # Fallback: keep all stations if filter is too aggressive
        print("   ⚠️  Too few stations after filter — keeping all stations")
        stations_filtered = stations_df.copy()
    
    stations_filtered[['id','name','lat','lon','zone','capacity']].to_csv('data/stations.csv', index=False)
    print(f"   Updated stations.csv: {len(stations_filtered)} active stations")

    # ── Build delays.csv from schedule data ──────────────────────
    # Real delays aren't in this dataset, but we can build realistic synthetic delays
    # anchored to real train numbers and station codes from schedules
    np.random.seed(42)
    train_nos = sched_df['train_no'].dropna().unique()
    station_codes = sched_df['station'].dropna().unique()

    # Map train type to realistic delay distribution
    # Express/Rajdhani → lower avg delay; Passenger → higher
    def get_delay(train_no):
        t = str(train_no)
        t_num = ''.join(c for c in t if c.isdigit())
        num = int(t_num) if t_num else 0
        
        # Rajdhani trains (12951, 12301 etc) — premium, lower delays
        if t.startswith('12') and num in range(12000, 13000):
            return max(0, int(np.random.exponential(8)))
        # Mail/Express
        elif t.startswith('1'):
            return max(0, int(np.random.exponential(18)))
        # Passenger trains
        else:
            return max(0, int(np.random.exponential(30)))

    delay_records = []
    for _ in range(5000):
        train_no = random.choice(train_nos)
        station  = random.choice(station_codes)
        delay    = get_delay(train_no)
        delay_records.append({
            'train_no':  train_no,
            'station':   station,
            'date':      pd.Timestamp('2024-01-01') + pd.Timedelta(days=np.random.randint(0, 365)),
            'delay_min': delay,
            'reason':    random.choice(['signal','track','passenger','weather','loco']),
            'weather':   random.choice(['clear','rain','fog']),
            'season':    random.choice(['summer','monsoon','winter']),
        })

    delays_df = pd.DataFrame(delay_records)
    delays_df.to_csv('data/delays.csv', index=False)
    print(f"✅ Delays: {len(delays_df)} records built (anchored to {len(train_nos)} real trains)")
    print(f"   Avg delay: {delays_df['delay_min'].mean():.1f} min")

    return sched_df, stations_filtered


# ════════════════════════════════════════════════════════════════
# 4. PNR DATA  →  data/pnr.csv
# If you got Aaryan's ticket dataset, put it at data/raw/tickets_raw.csv
# Otherwise we generate realistic synthetic PNR anchored to real train numbers
# ════════════════════════════════════════════════════════════════
def adapt_or_generate_pnr(trains_df):
    print("\n── Adapting PNR / Ticket Data ──")

    TICKETS_RAW = 'data/raw/tickets_raw.csv'

    if os.path.exists(TICKETS_RAW):
        print("   Found real ticket data — adapting...")
        df = pd.read_csv(TICKETS_RAW)
        df.columns = df.columns.str.lower().str.strip()

        col_map = {
            'wl_number': 'wl_number', 'waitlist_no': 'wl_number', 'wl_no': 'wl_number',
            'class': 'travel_class',  'travel_class': 'travel_class',
            'confirmed': 'confirmed',  'status': 'confirmed',
            'train_no': 'train_no',   'train_number': 'train_no',
            'quota': 'quota',
        }
        df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})

        if 'confirmed' in df.columns and df['confirmed'].dtype == object:
            df['confirmed'] = df['confirmed'].str.upper().map(
                lambda x: 1 if x in ['CNF','CONFIRMED','1','YES'] else 0
            )

        # Fill any missing columns
        if 'days_ahead'  not in df.columns: df['days_ahead']  = np.random.randint(1, 120, len(df))
        if 'season_peak' not in df.columns: df['season_peak'] = np.random.choice([0,0,0,1], len(df))
        if 'travel_class' not in df.columns: df['travel_class'] = 'SL'
        if 'quota'       not in df.columns: df['quota']       = 'General'
        if 'wl_number'   not in df.columns: df['wl_number']   = np.random.randint(1, 120, len(df))

        df = df.dropna(subset=['confirmed'])
        df['confirmed'] = df['confirmed'].astype(int)

    else:
        print("   No real ticket file found — generating synthetic PNR anchored to real train numbers")
        real_train_nos = trains_df['train_no'].dropna().unique().tolist() if trains_df is not None else ['12301']
        classes = ['SL','3A','2A','1A']
        quotas  = ['General','Ladies','Tatkal']

        records = []
        for _ in range(10000):
            wl         = np.random.randint(1, 120)
            days_ahead = np.random.randint(1, 120)
            season     = random.choice([0, 0, 0, 1])
            # Realistic probability formula (same as synthetic generator)
            p = max(0.0, min(1.0, 0.95 - 0.008*wl + 0.003*days_ahead - 0.2*season))
            confirmed = int(np.random.random() < p)
            records.append({
                'wl_number':    wl,
                'train_no':     random.choice(real_train_nos),  # ← real train numbers
                'travel_class': random.choice(classes),
                'quota':        random.choice(quotas),
                'days_ahead':   days_ahead,
                'season_peak':  season,
                'confirmed':    confirmed,
            })
        df = pd.DataFrame(records)

    df[['wl_number','train_no','travel_class','quota',
        'days_ahead','season_peak','confirmed']].to_csv('data/pnr.csv', index=False)

    conf_rate = df['confirmed'].mean()
    print(f"✅ PNR: {len(df)} records saved | Confirmation rate: {conf_rate:.1%}")
    return df


# ════════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════════
if __name__ == '__main__':
    print("=" * 55)
    print("  Sripaad Indian Railways Dataset Adapter")
    print("=" * 55)

    # Check files exist
    missing = []
    for label, path in [('stations', STATIONS_JSON), ('trains', TRAINS_JSON), ('schedules', SCHEDULES_JSON)]:
        if not os.path.exists(path):
            missing.append(f"  ✗  {label}: {path}")
    if missing:
        print("\n⚠️  Missing files — check your paths at the top of this script:")
        print('\n'.join(missing))
        print("\nExpected structure:")
        print("  data/raw/stations.json")
        print("  data/raw/trains.json")
        print("  data/raw/schedules.json")
        exit(1)

    stations_df            = adapt_stations()
    trains_df, routes_df   = adapt_trains_and_routes()
    sched_df, stations_df  = adapt_schedules_and_delays(stations_df, trains_df)
    pnr_df                 = adapt_or_generate_pnr(trains_df)

    print("\n" + "=" * 55)
    print("  All files ready in data/")
    print("=" * 55)
    print("  stations.csv  →  graph nodes")
    print("  routes.csv    →  graph edges")
    print("  delays.csv    →  delay model training")
    print("  pnr.csv       →  ticket model training")
    print("\n  Next: retrain your models")
    print("  python -c \"")
    print("  from backend.graph.railway_graph import RailwayGraph")
    print("  from backend.models.delay_model import DelayCascadeModel")
    print("  from backend.models.ticket_model import TicketConfirmationModel")
    print("  rg = RailwayGraph()")
    print("  G  = rg.build_from_csv('data/stations.csv','data/routes.csv')")
    print("  dm = DelayCascadeModel(G); dm.train('data/delays.csv')")
    print("  tm = TicketConfirmationModel(); tm.train('data/pnr.csv')")
    print("  print('Done')\"")
    