# data/adapt_ticket_data.py
# Adapter for Aaryan Anil's Railway Ticket Confirmation dataset
# Run: python data/adapt_ticket_data.py

import pandas as pd
import numpy as np
import os

RAW_PATH = 'data/raw/Railway Ticket Confirmation.csv'# ← rename your downloaded file to this
OUT_PATH = 'data/pnr.csv'

print("── Adapting Aaryan's Ticket Dataset ──")

df = pd.read_csv(RAW_PATH)
print(f"Raw shape: {df.shape}")

# ── 1. TARGET: Confirmation Status → 0/1 ─────────────────────────
df['confirmed'] = (df['Confirmation Status'] == 'Confirmed').astype(int)
print(f"Confirmation rate: {df['confirmed'].mean():.1%}")

# ── 2. WL NUMBER: Extract integer from 'WL097' format ────────────
# NaN = ticket was confirmed/RAC from start (no waitlist) → set to 0
df['wl_number'] = df['Waitlist Position'].str.extract(r'(\d+)').astype(float).fillna(0).astype(int)
print(f"WL range: {df['wl_number'].min()} – {df['wl_number'].max()}")

# ── 3. PEAK SEASON: Yes/No → 1/0 ─────────────────────────────────
df['season_peak'] = (df['Holiday or Peak Season'] == 'Yes').astype(int)

# ── 4. CLASS ENCODING ─────────────────────────────────────────────
class_map = {'Sleeper': 0, '3AC': 1, '2AC': 2, '1AC': 3}
df['class_enc'] = df['Class of Travel'].map(class_map).fillna(0).astype(int)

# ── 5. QUOTA ENCODING ────────────────────────────────────────────
quota_map = {'General': 0, 'Ladies': 1, 'Tatkal': 2, 'Premium Tatkal': 3}
df['quota_enc'] = df['Quota'].map(quota_map).fillna(0).astype(int)

# ── 6. TRAIN TYPE ENCODING ───────────────────────────────────────
type_map = {'Express': 0, 'Superfast': 1, 'Shatabdi': 2, 'Rajdhani': 3}
df['train_type_enc'] = df['Train Type'].map(type_map).fillna(0).astype(int)

# ── 7. BOOKING CHANNEL ───────────────────────────────────────────
channel_map = {'Counter': 0, 'Mobile App': 1, 'IRCTC Website': 2}
df['channel_enc'] = df['Booking Channel'].map(channel_map).fillna(0).astype(int)

# ── 8. AGE OF PASSENGERS ─────────────────────────────────────────
age_map = {'Child': 0, 'Adult': 1, 'Senior Citizen': 2}
df['age_enc'] = df['Age of Passengers'].map(age_map).fillna(1).astype(int)

# ── 9. SPECIAL CONSIDERATIONS ────────────────────────────────────
df['has_special'] = df['Special Considerations'].notna().astype(int)

# ── 10. NUMERIC FEATURES (already clean) ─────────────────────────
df['travel_distance']   = df['Travel Distance'].astype(int)
df['travel_time']       = df['Travel Time'].astype(int)
df['seat_availability'] = df['Seat Availability'].astype(int)
df['num_passengers']    = df['Number of Passengers'].astype(int)

# ── NOTE: days_ahead is constant (244) in this dataset ───────────
# We keep it for schema compatibility but it won't affect predictions
df['days_ahead'] = 244

# ── SAVE ─────────────────────────────────────────────────────────
out_cols = [
    'wl_number', 'Train Number', 'class_enc', 'quota_enc',
    'train_type_enc', 'channel_enc', 'age_enc', 'has_special',
    'travel_distance', 'travel_time', 'seat_availability',
    'num_passengers', 'season_peak', 'days_ahead', 'confirmed'
]
# Rename Train Number for schema consistency
df = df.rename(columns={'Train Number': 'train_no'})
out_cols[1] = 'train_no'

df[out_cols].to_csv(OUT_PATH, index=False)

print(f"\n✅ Saved {len(df)} records to {OUT_PATH}")
print(f"   Features: {len(out_cols)-1} input columns + 1 target")
print(f"   Confirmed: {df['confirmed'].sum():,}  |  Not confirmed: {(1-df['confirmed']).sum():,}")
print(f"\n   Top feature correlation with confirmation:")
corr = df[['wl_number','season_peak','seat_availability','travel_distance','confirmed']].corr()['confirmed']
print(corr.drop('confirmed').sort_values().to_string())