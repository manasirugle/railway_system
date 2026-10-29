import numpy as np, pandas as pd, random
  
  # ── STATIONS ──────────────────────────────────────────────────
stations = [
      {'id': 'NDLS', 'name': 'New Delhi',    'lat': 28.64, 'lon': 77.22, 'zone': 'NR', 'capacity': 500},
      {'id': 'MMCT', 'name': 'Mumbai CST',   'lat': 18.94, 'lon': 72.83, 'zone': 'CR', 'capacity': 600},
      {'id': 'MAS',  'name': 'Chennai Ctrl', 'lat': 13.08, 'lon': 80.27, 'zone': 'SR', 'capacity': 400},
      {'id': 'HWH',  'name': 'Howrah',       'lat': 22.58, 'lon': 88.34, 'zone': 'ER', 'capacity': 450},
      {'id': 'CNB',  'name': 'Kanpur Ctrl',  'lat': 26.46, 'lon': 80.35, 'zone': 'NCR','capacity': 300},
      {'id': 'BSB',  'name': 'Varanasi',     'lat': 25.31, 'lon': 83.01, 'zone': 'NER','capacity': 280},
      {'id': 'NGP',  'name': 'Nagpur',       'lat': 21.14, 'lon': 79.08, 'zone': 'CR', 'capacity': 320},
      {'id': 'SC',   'name': 'Secunderabad', 'lat': 17.43, 'lon': 78.50, 'zone': 'SCR','capacity': 380},
      {'id': 'ADI',  'name': 'Ahmedabad',    'lat': 23.02, 'lon': 72.57, 'zone': 'WR', 'capacity': 350},
      {'id': 'JP',   'name': 'Jaipur',       'lat': 26.92, 'lon': 75.79, 'zone': 'NWR','capacity': 260},
  ]
  
  # ── ROUTES (edges) ────────────────────────────────────────────
routes = [
      {'from': 'NDLS', 'to': 'CNB',  'distance': 440, 'travel_hrs': 4.5, 'capacity': 50},
      {'from': 'CNB',  'to': 'BSB',  'distance': 210, 'travel_hrs': 3.0, 'capacity': 40},
      {'from': 'CNB',  'to': 'HWH',  'distance': 960, 'travel_hrs': 9.5, 'capacity': 45},
      {'from': 'NDLS', 'to': 'ADI',  'distance': 940, 'travel_hrs': 10., 'capacity': 55},
      {'from': 'ADI',  'to': 'MMCT', 'distance': 540, 'travel_hrs': 7.5, 'capacity': 60},
      {'from': 'NDLS', 'to': 'JP',   'distance': 310, 'travel_hrs': 4.0, 'capacity': 45},
      {'from': 'MMCT', 'to': 'NGP',  'distance': 870, 'travel_hrs': 11., 'capacity': 50},
      {'from': 'NGP',  'to': 'SC',   'distance': 490, 'travel_hrs': 6.5, 'capacity': 45},
      {'from': 'SC',   'to': 'MAS',  'distance': 710, 'travel_hrs': 9.0, 'capacity': 50},
      {'from': 'MAS',  'to': 'HWH',  'distance': 1660,'travel_hrs': 25., 'capacity': 40},
  ]
  
  # ── TRAIN SCHEDULES ──────────────────────────────────────────
trains = []
train_templates = [
      ('12301', 'Rajdhani', ['NDLS','CNB','BSB','HWH'], 'Express'),
      ('12951', 'Mumbai Rajdhani', ['NDLS','ADI','MMCT'], 'Rajdhani'),
      ('12621', 'Tamil Nadu Exp', ['NDLS','CNB','SC','MAS'], 'Express'),
      ('12723', 'Telangana Exp', ['SC','NGP','CNB','NDLS'], 'Express'),
      ('12901', 'Gujarat Mail', ['MMCT','ADI','JP','NDLS'], 'Mail'),
  ]
for tn, name, stops, cat in train_templates:
      for day in range(7):
          trains.append({'train_no': tn, 'name': name, 'stops': stops,
                          'category': cat, 'day': day,
                          'scheduled_dep': f'2025-01-{day+1:02d} 06:00'})
  
  # ── DELAY HISTORY ────────────────────────────────────────────
np.random.seed(42)
delay_records = []
for _ in range(5000):
      train = random.choice(train_templates)
      delay_records.append({
          'train_no':     train[0],
          'station':      random.choice(train[2]),
          'date':         pd.Timestamp('2024-01-01') + pd.Timedelta(days=np.random.randint(0,365)),
          'delay_min':    max(0, int(np.random.exponential(15))),  # avg 15 min delay
          'reason':       random.choice(['signal','track','passenger','weather','loco']),
          'weather':      random.choice(['clear','rain','fog']),
          'season':       random.choice(['summer','monsoon','winter']),
      })
  
  # ── PNR / TICKET DATA ────────────────────────────────────────
pnr_records = []
classes = ['SL', '3A', '2A', '1A']
quotas  = ['General', 'Ladies', 'Tatkal']
for _ in range(10000):
      wl = np.random.randint(1, 120)
      days_ahead = np.random.randint(1, 120)
      season_peak = random.choice([0, 0, 0, 1])  # 25% peak season
      # Realistic confirmation probability
      p = max(0.0, min(1.0, 0.95 - 0.008*wl + 0.003*days_ahead - 0.2*season_peak))
      confirmed = int(np.random.random() < p)
      pnr_records.append({
          'wl_number':   wl,
          'train_no':    random.choice([t[0] for t in train_templates]),
          'travel_class':random.choice(classes),
          'quota':       random.choice(quotas),
          'days_ahead':  days_ahead,
          'season_peak': season_peak,
          'confirmed':   confirmed,
      })
  
  # Save all
pd.DataFrame(stations).to_csv('stations.csv', index=False)
pd.DataFrame(routes).to_csv('routes.csv', index=False)
pd.DataFrame(delay_records).to_csv('delays.csv', index=False)
pd.DataFrame(pnr_records).to_csv('pnr.csv', index=False)
print('✅ Synthetic data generated: stations, routes, delays, pnr')
