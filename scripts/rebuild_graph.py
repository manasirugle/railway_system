import json, pandas as pd, numpy as np, random, os

print('=== Rebuilding from Sripaad schedules.json ===')

# ── Load all 3 Sripaad files ──────────────────────────────────────
with open('data/raw/stations.json') as f: stn_geo = json.load(f)
with open('data/raw/schedules.json') as f: schedules = json.load(f)
with open('data/raw/trains.json') as f: trains_geo = json.load(f)

# ── Build station lookup: code → {lat, lon, zone, name} ──────────
stn_lookup = {}
stn_features = stn_geo.get('features', []) if isinstance(stn_geo, dict) else stn_geo
for feat in stn_features:
    try:
        p = feat.get('properties', {})
        code = p.get('code','').strip().upper()
        g = feat.get('geometry', {})
        if not g: continue
        coords = g.get('coordinates', [])
        if len(coords) < 2: continue
        lon, lat = coords[0], coords[1]
        if code:
            stn_lookup[code] = {
                'id': code, 'name': p.get('name',''), 
                'lat': lat, 'lon': lon,
                'zone': p.get('zone','NR'), 'capacity': 300
            }
    except Exception as e:
        pass
print(f'Station lookup: {len(stn_lookup)} entries')

# ── Build train type lookup from trains.json ──────────────────────
train_type_map = {}
train_features = trains_geo.get('features', []) if isinstance(trains_geo, dict) else trains_geo
for feat in train_features:
    try:
        p = feat.get('properties', {})
        no = str(p.get('number','')).strip()
        name = str(p.get('name','')).upper()
        if 'RAJDHANI' in name:   t = 'Rajdhani'
        elif 'SHATABDI' in name: t = 'Shatabdi'
        elif 'SUPERFAST' in name or ' SF' in name: t = 'Superfast'
        elif 'MAIL' in name:     t = 'Mail'
        else:                    t = 'Express'
        train_type_map[no] = t
    except Exception as e:
        pass

# ── Build routes from consecutive schedule stops ──────────────────
# Sort each train's stops by day+departure, then take consecutive pairs
sched_df = pd.DataFrame(schedules if isinstance(schedules, list) else schedules.get('features',[]))
print(f'Schedule records: {len(sched_df)}')
print(f'Columns: {list(sched_df.columns)}')

# Normalise column names
sched_df.columns = sched_df.columns.str.lower()
col_remap = {
    'train_number':'train_no','trainNumber':'train_no',
    'station_code':'station', 'stationCode':'station',
    'departure':'departure',  'departs':'departure',
}
sched_df = sched_df.rename(columns={k:v for k,v in col_remap.items() if k in sched_df.columns})

def parse_hhmm(t):
    try:
        parts = str(t).split(':')
        return int(parts[0])*60 + int(parts[1])
    except: return None

sched_df['dep_min'] = sched_df['departure'].apply(parse_hhmm)
sched_df['day']     = pd.to_numeric(sched_df.get('day', pd.Series([1]*len(sched_df))), errors='coerce').fillna(1).astype(int)
sched_df['sort_key'] = sched_df['day']*1440 + sched_df['dep_min'].fillna(0)

print('Building route segments...')
route_segments = {}
for train_no, grp in sched_df.groupby('train_no'):
    stops = grp.sort_values('sort_key')['station'].str.upper().str.strip().tolist()
    for i in range(len(stops)-1):
        a, b = stops[i], stops[i+1]
        if a and b and a != b:
            key = (a, b)
            route_segments[key] = route_segments.get(key, 0) + 1

print(f'Raw segment pairs: {len(route_segments)}')

# Only keep segments where both stations exist in Sripaad station data
valid = {(a,b):cnt for (a,b),cnt in route_segments.items() 
         if a in stn_lookup and b in stn_lookup}
print(f'Segments with known coordinates: {len(valid)}')

# Build routes.csv
route_rows = []
for (a, b), cnt in valid.items():
    sa, sb = stn_lookup[a], stn_lookup[b]
    # Haversine distance estimate
    import math
    lat1,lon1 = math.radians(sa['lat']), math.radians(sa['lon'])
    lat2,lon2 = math.radians(sb['lat']), math.radians(sb['lon'])
    dlat, dlon = lat2-lat1, lon2-lon1
    hav = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
    dist_km = round(2*6371*math.asin(math.sqrt(hav)), 1)
    travel_hrs = round(dist_km / 60.0, 2)   # avg 60 km/h
    route_rows.append({'from':a,'to':b,'distance':dist_km,
                       'travel_hrs':travel_hrs,'capacity':50,'num_trains':cnt})

routes_df = pd.DataFrame(route_rows)
routes_df = routes_df[routes_df['distance'].between(5, 1500)]
routes_df.to_csv('data/routes.csv', index=False)
print(f'Routes saved: {len(routes_df)}')

# ── Build balanced stations.csv ───────────────────────────────────
# Only keep stations that actually appear in routes (have real train traffic)
active_codes = set(routes_df['from'].tolist() + routes_df['to'].tolist())
active_stns  = [stn_lookup[c] for c in active_codes if c in stn_lookup]
s_df = pd.DataFrame(active_stns)

# Zone-balanced: top 15 per zone, max 250 total
zone_capacity_map = {
    'NR':500,'CR':480,'WR':460,'SR':440,'ER':430,'SCR':400,
    'SER':390,'NWR':370,'NCR':380,'NER':300,'NFR':280,'ECR':320,
    'ECoR':310,'SWR':340,'WCR':330,'SECR':320,'KR':300
}
s_df['capacity'] = s_df['zone'].map(zone_capacity_map).fillna(300).astype(int)

valid_zones = list(zone_capacity_map.keys())
s_df = s_df[s_df['zone'].isin(valid_zones)]
s_df = (s_df.groupby('zone', group_keys=False)
        .apply(lambda x: x.head(15))
        .reset_index(drop=True))

# Hardcode 8 critical demo stations (inject if missing)
key_stations = [
    {'id':'NDLS','name':'New Delhi',      'lat':28.6420,'lon':77.2197,'zone':'NR', 'capacity':500},
    {'id':'CSTM','name':'Mumbai CST',     'lat':18.9398,'lon':72.8355,'zone':'CR', 'capacity':600},
    {'id':'MAS', 'name':'Chennai Central','lat':13.0827,'lon':80.2707,'zone':'SR', 'capacity':440},
    {'id':'HWH', 'name':'Howrah Jn',      'lat':22.5839,'lon':88.3425,'zone':'ER', 'capacity':450},
    {'id':'CNB', 'name':'Kanpur Central', 'lat':26.4582,'lon':80.3467,'zone':'NCR','capacity':380},
    {'id':'SC',  'name':'Secunderabad',   'lat':17.4344,'lon':78.5013,'zone':'SCR','capacity':390},
    {'id':'ADI', 'name':'Ahmedabad Jn',   'lat':23.0225,'lon':72.5714,'zone':'WR', 'capacity':460},
    {'id':'JP',  'name':'Jaipur Jn',      'lat':26.9215,'lon':75.7873,'zone':'NWR','capacity':370},
]
existing_ids = set(s_df['id'].tolist())
injected = []
for ks in key_stations:
    if ks['id'] not in existing_ids:
        injected.append(ks)
        print(f'  Injected key station: {ks["id"]} ({ks["name"]})')

if injected:
    s_df = pd.concat([s_df, pd.DataFrame(injected)], ignore_index=True)

s_df.to_csv('data/stations.csv', index=False)
print(f'Stations saved: {len(s_df)} | Zones: {sorted(s_df["zone"].unique())}')

# Final route filter with new station set
valid_ids = set(s_df['id'])
r_final = routes_df[routes_df['from'].isin(valid_ids) & routes_df['to'].isin(valid_ids)]
r_final.to_csv('data/routes.csv', index=False)
print(f'Final routes: {len(r_final)}')
print()
print('Key station check:')
for ks in key_stations:
    tag = 'OK' if ks['id'] in valid_ids else 'MISSING'
    print(f'  {ks["id"]:6} {ks["name"]:20} [{tag}]')
    
# Retrain the models for the changes!
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.graph.railway_graph import RailwayGraph
from backend.models.delay_model import DelayCascadeModel
from backend.models.ticket_model import TicketConfirmationModel

print("Retraining graph models to make sure it loads smoothly")
rg = RailwayGraph()
G  = rg.build_from_csv('data/stations.csv', 'data/routes.csv')
print('Graph:', G.number_of_nodes(), 'nodes,', G.number_of_edges(), 'edges')

dm = DelayCascadeModel(G); dm.train('data/delays.csv')
tm = TicketConfirmationModel(); tm.train('data/pnr.csv')

print('All models ready ✅')
