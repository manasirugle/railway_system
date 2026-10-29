import numpy as np, pandas as pd
from xgboost import XGBRegressor
from sklearn.model_selection import train_test_split
from collections import deque
import joblib

class DelayCascadeModel:

    def __init__(self, graph):
        self.G     = graph
        self.model = XGBRegressor(n_estimators=200, max_depth=5, random_state=42)

    def _encode_features(self, df):
        df['reason_enc']  = pd.Categorical(df['reason']).codes
        df['weather_enc'] = pd.Categorical(df['weather']).codes
        df['season_enc']  = pd.Categorical(df['season']).codes
        return df

    def train(self, delays_path):
        df = pd.read_csv(delays_path)
        df = self._encode_features(df)
        features = ['reason_enc','weather_enc','season_enc']
        # Add engineered features
        df['hour'] = pd.to_datetime(df['date']).dt.hour
        df['dow']  = pd.to_datetime(df['date']).dt.dayofweek
        features  += ['hour','dow']
        X = df[features].fillna(0)
        y = df['delay_min'].clip(0, 300)  # cap at 5 hours
        X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.2)
        self.model.fit(X_tr, y_tr, eval_set=[(X_te, y_te)], verbose=False)
        print(f'Delay model trained. Test R²: {self.model.score(X_te, y_te):.3f}')
        joblib.dump(self.model, 'backend/models/saved/delay_model.pkl')

    def predict_single(self, reason='signal', weather='clear', season='winter',
                        hour=8, dow=1):
        reason_map  = {'signal':0,'track':1,'passenger':2,'weather':3,'loco':4}
        weather_map = {'clear':0,'rain':1,'fog':2}
        season_map  = {'summer':0,'monsoon':1,'winter':2}
        X = np.array([[reason_map.get(reason,0), weather_map.get(weather,0),
                        season_map.get(season,0), hour, dow]])
        return float(self.model.predict(X)[0])

    def simulate_cascade(self, origin_station, initial_delay_min,
                          reason='signal', weather='clear', season='winter'):
        '''BFS cascade: propagate delay through downstream stations'''
        cascade = {origin_station: initial_delay_min}
        queue   = deque([(origin_station, initial_delay_min)])
        visited = {origin_station}
        DECAY   = 0.65  # each hop loses 35% of delay

        while queue:
            station, delay = queue.popleft()
            if delay < 2:  # stop propagating tiny delays
                continue
            for neighbor in self.G.successors(station):
                if neighbor not in visited:
                    edge = self.G[station][neighbor]
                    # capacity multiplier: fuller corridors amplify delay
                    cap_mult = 1.0 + (edge.get('capacity',50) / 100.0) * 0.3
                    propagated = delay * DECAY * cap_mult
                    cascade[neighbor] = round(propagated, 1)
                    visited.add(neighbor)
                    queue.append((neighbor, propagated))

        return cascade  # {station_id: delay_minutes}

    def get_vulnerable_routes(self, top_n=5):
        '''Stations with highest cascade amplification potential'''
        scores = {}
        for node in self.G.nodes():
            cascade = self.simulate_cascade(node, 60)  # simulate 1h delay
            total_impact = sum(cascade.values())
            scores[node] = total_impact
        return sorted(scores.items(), key=lambda x: -x[1])[:top_n]
