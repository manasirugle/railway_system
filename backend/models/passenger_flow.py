import numpy as np
import pandas as pd

FESTIVAL_DAYS = [
    '2025-01-14',  # Makar Sankranti
    '2025-03-14',  # Holi
    '2025-08-15',  # Independence Day
    '2025-10-02',  # Gandhi Jayanti
    '2025-10-20',  # Diwali (approx)
    '2025-12-25',  # Christmas
    '2026-01-14',  # Makar Sankranti
    '2026-03-03',  # Holi
]

PEAK_HOURS = list(range(7, 10)) + list(range(17, 21))  # 7–9am, 5–8pm


class PassengerFlowModel:

    def __init__(self, stations, routes):
        """
        stations: list of dicts or DataFrame records with keys:
                  id, name, lat, lon, zone, capacity
        routes:   list of dicts or DataFrame records with keys:
                  from, to, distance, travel_hrs, capacity
        """
        # Normalise to list of dicts regardless of input type
        if isinstance(stations, pd.DataFrame):
            self.stations = stations.to_dict('records')
        else:
            self.stations = list(stations)

        if isinstance(routes, pd.DataFrame):
            self.routes = routes.to_dict('records')
        else:
            self.routes = list(routes)

        self._station_index = {s['id']: s for s in self.stations}
        self.od_matrix = self._build_od_matrix()

    # Internal helpers

    def _build_od_matrix(self):
        """
        Gravity-model OD matrix.
        Demand ∝ sqrt(capacity_i × capacity_j), scaled by route connectivity.
        Only pairs connected by at least one route segment get non-zero demand.
        """
        ids = [s['id'] for s in self.stations]
        n = len(ids)
        idx = {sid: i for i, sid in enumerate(ids)}
        M = np.zeros((n, n))

        # Build adjacency set from routes
        connected = set()
        for r in self.routes:
            connected.add((r['from'], r['to']))
            connected.add((r['to'], r['from']))  # bidirectional

        for i, si in enumerate(self.stations):
            for j, sj in enumerate(self.stations):
                if i == j:
                    continue
                ci = si.get('capacity', 100)
                cj = sj.get('capacity', 100)
                base = (ci * cj) ** 0.5 * np.random.uniform(0.8, 1.2)
                # Boost directly connected pairs
                if (si['id'], sj['id']) in connected:
                    base *= 1.5
                M[i][j] = base

        return pd.DataFrame(M, index=ids, columns=ids)

    def _festival_multiplier(self, date_str):
        return 1.8 if date_str in FESTIVAL_DAYS else 1.0

    def _hour_multiplier(self, hour):
        return 1.5 if hour in PEAK_HOURS else 1.0

    # Public API (called by PassengerIntelligenceEngine + FastAPI)

    def get_station_crowd(self, station_id, date_str, hour=8):
        """
        Returns crowd estimate for a station at a given hour/date.
        station_id: e.g. 'NDLS'
        date_str:   'YYYY-MM-DD'
        hour:       int 0–23
        """
        if station_id not in self.od_matrix.columns:
            return {
                'station': station_id,
                'crowd_score': 0.0,
                'level': 'UNKNOWN',
                'hour': hour,
                'festival': False,
                'error': f'Station {station_id} not found in OD matrix'
            }

        base = float(self.od_matrix[station_id].sum())
        h_mult = self._hour_multiplier(hour)
        f_mult = self._festival_multiplier(date_str)
        crowd = base * h_mult * f_mult / 1000  # normalise

        level = 'HIGH' if crowd > 70 else 'MEDIUM' if crowd > 35 else 'LOW'
        return {
            'station': station_id,
            'crowd_score': round(crowd, 1),
            'level': level,
            'hour': hour,
            'festival': f_mult > 1.0,
        }

    def get_route_demand(self, from_id, to_id, date_str):
        """
        Returns estimated passenger demand between two stations.
        """
        if from_id not in self.od_matrix.index or to_id not in self.od_matrix.columns:
            return {
                'route': f'{from_id}→{to_id}',
                'demand': 0,
                'festival_surge': False,
                'error': 'One or both stations not found'
            }

        base = float(self.od_matrix.loc[from_id, to_id])
        is_fest = date_str in FESTIVAL_DAYS
        demand = base * (1.9 if is_fest else 1.0)
        return {
            'route': f'{from_id}→{to_id}',
            'demand': round(demand),
            'festival_surge': is_fest,
        }

    def get_top_crowded_stations(self, date_str, hour=8, top_n=5):
        """
        Returns top-N most crowded stations for a given time window.
        Useful for dashboard Tab 2 crowd heatmap.
        """
        scores = []
        for s in self.stations:
            result = self.get_station_crowd(s['id'], date_str, hour)
            scores.append(result)
        return sorted(scores, key=lambda x: -x['crowd_score'])[:top_n]

    def get_od_summary(self, top_n=10):
        """
        Returns top-N origin-destination pairs by demand.
        Useful for operators to see busiest corridors.
        """
        records = []
        for from_id in self.od_matrix.index:
            for to_id in self.od_matrix.columns:
                if from_id == to_id:
                    continue
                demand = float(self.od_matrix.loc[from_id, to_id])
                records.append({
                    'from': from_id,
                    'to': to_id,
                    'demand': round(demand)
                })
        return sorted(records, key=lambda x: -x['demand'])[:top_n]