# backend/models/congestion_model.py
import pandas as pd
import numpy as np
from prophet import Prophet
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

class CongestionModel:
    def __init__(self):
        self.models    = {}
        self.forecasts = {}

    def _generate_corridor_data(self, corridor, days=90):
        '''Synthetic hourly load anchored to realistic Indian Railways patterns'''
        dates, loads = [], []
        base = datetime(2024, 10, 1)
        # Extract station names for corridor label
        parts = corridor.split('-')
        for d in range(days * 24):
            dt   = base + timedelta(hours=d)
            hour = dt.hour
            dow  = dt.weekday()
            month = dt.month
            # Morning peak 6-10, evening peak 17-21
            hour_load = 40 + 25 * np.exp(-((hour-8)**2)/8) + \
                           20 * np.exp(-((hour-19)**2)/8)
            # Weekend boost
            weekend_boost = 8 if dow >= 5 else 0
            # Winter fog season (Dec-Feb) causes cascading delays → higher load
            season_boost  = 10 if month in [12, 1, 2] else \
                             8 if month in [6, 7, 8] else 0  # monsoon
            load = hour_load + weekend_boost + season_boost
            load += np.random.normal(0, 4)
            dates.append(dt)
            loads.append(max(10, load))
        return pd.DataFrame({'ds': dates, 'y': loads})

    def train_corridor(self, corridor):
        df = self._generate_corridor_data(corridor)
        m  = Prophet(
            changepoint_prior_scale=0.1,
            seasonality_mode='multiplicative',
            daily_seasonality=True,
            weekly_seasonality=True,
        )
        m.fit(df)
        self.models[corridor] = m

    def forecast_next_24h(self, corridor):
        if corridor not in self.models:
            self.train_corridor(corridor)
        model  = self.models[corridor]
        future = model.make_future_dataframe(periods=24, freq='h')
        fc     = model.predict(future).tail(24)
        self.forecasts[corridor] = fc
        return fc[['ds','yhat','yhat_lower','yhat_upper']].to_dict('records')

    def get_congestion_hotspots(self, corridors, top_n=5):
        '''Rank corridors by forecast peak load in next 24h'''
        peak_loads = {}
        for c in corridors:
            fc = self.forecast_next_24h(c)
            peak_loads[c] = max(r['yhat'] for r in fc)

        ranked = sorted(peak_loads.items(), key=lambda x: -x[1])
        return [
            {
                'corridor':       c,
                'peak_load':      round(v, 1),
                'congestion_pct': min(100, round(v / 120 * 100, 1)),
                'status':         'CRITICAL' if v > 70 else
                                  'HIGH'     if v > 55 else
                                  'MEDIUM'   if v > 40 else 'LOW'
            }
            for c, v in ranked[:top_n]
        ]


if __name__ == '__main__':
    cm = CongestionModel()

    # Use real station pairs from your graph
    corridors = [
        'NDLS-CNB', 'NDLS-ADI', 'CNB-HWH',
        'ADI-CSTM', 'SC-MAS',   'NDLS-JP'
    ]

    print('Training congestion models...')
    hotspots = cm.get_congestion_hotspots(corridors)

    print('\nCongestion Hotspots (Next 24h):')
    for h in hotspots:
        print(f"  {h['corridor']:12} | {h['congestion_pct']:5.1f}% | {h['status']}")

    print('\n24h forecast sample (NDLS-CNB):')
    fc = cm.forecast_next_24h('NDLS-CNB')
    for row in fc[6:10]:   # show hours 6-9
        print(f"  {str(row['ds'])[-8:-3]}  load={row['yhat']:.1f}")

    print('\nCongestion model ✅')