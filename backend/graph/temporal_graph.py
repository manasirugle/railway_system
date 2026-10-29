import networkx as nx
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from .railway_graph import RailwayGraph

class TemporalRailwayGraph(RailwayGraph):
    def __init__(self):
        super().__init__()
        self.train_db = None
        self.delay_db = None
        self.active_trains = []  # List of dicts representing moving trains
        self.current_time = datetime(2024, 1, 1, 0, 0, 0) # Simulation start

    def build_temporal_model(self, stations_path, routes_path, trains_path, delays_path):
        """Construct the base graph and load temporal data."""
        print(f"Loading stations from {stations_path}...")
        self.build_from_csv(stations_path, routes_path)
        print(f"Loading trains from {trains_path}...")
        self.train_db = pd.read_csv(trains_path)
        print(f"Loading delays from {delays_path}...")
        self.delay_db = pd.read_csv(delays_path)
        # Filter trains to only those where origin and destination are in our station list
        valid_stations = set(self.G.nodes())
        self.train_db = self.train_db[
            self.train_db['origin'].isin(valid_stations) & 
            self.train_db['destination'].isin(valid_stations)
        ]
        print(f"Loaded {len(self.train_db)} valid trains for temporal modeling.")

    def get_corridor_connectivity(self):
        """Analyze connectivity between major corridors."""
        # Define major corridors by zones or key hubs
        # For simplicity, we define North (NDLS), South (MAS), East (HWH), West (CSTM/ADI)
        hubs = {
            'North': 'NDLS',
            'South': 'MAS',
            'East': 'HWH',
            'West': ['CSTM', 'ADI']
        }
        
        connectivity = {}
        for region_a, hub_a in hubs.items():
            for region_b, hub_b in hubs.items():
                if region_a == region_b: continue
                
                # Handle cases where region has multiple hubs
                ha_list = hub_a if isinstance(hub_a, list) else [hub_a]
                hb_list = hub_b if isinstance(hub_b, list) else [hub_b]
                
                print(f"  Checking connectivity: {region_a} ({hub_a}) -> {region_b} ({hub_b})...")
                found = False
                for ha in ha_list:
                    for hb in hb_list:
                        if ha in self.G and hb in self.G:
                            try:
                                path_len = nx.shortest_path_length(self.G, ha, hb, weight='distance')
                                connectivity[f"{region_a} -> {region_b}"] = {
                                    "status": "Connected",
                                    "distance": f"{path_len:.1f} km",
                                    "hubs": f"{ha} to {hb}"
                                }
                                found = True
                                break
                            except nx.NetworkXNoPath:
                                continue
                    if found: break
                
                if not found:
                    connectivity[f"{region_a} -> {region_b}"] = {"status": "Disconnected"}
        
        return connectivity

    def get_train_movement_at(self, timestamp: datetime):
        """
        Simulate train positions at a specific time.
        Distributes trains uniformly along each edge using current minute
        for pseudo-temporal movement so positions shift each API call.
        NaN/missing values are sanitized before returning.
        """
        import math
        movements = []
        for u, v, d in self.G.edges(data=True):
            raw_trains = d.get('num_trains', 0)
            try:
                num_trains = int(raw_trains) if raw_trains and not math.isnan(float(raw_trains)) else 0
            except (TypeError, ValueError):
                num_trains = 0
            if num_trains <= 0:
                continue

            raw_dist = d.get('distance', 0)
            try:
                distance = float(raw_dist) if raw_dist and not math.isnan(float(raw_dist)) else 0.0
            except (TypeError, ValueError):
                distance = 0.0

            for i in range(min(num_trains, 5)):  # cap at 5 per edge to avoid flooding
                progress = (i / max(num_trains, 1) + timestamp.minute / 60.0) % 1.0
                movements.append({
                    "from": u,
                    "to":   v,
                    "progress":         round(progress, 2),
                    "distance_covered": round(progress * distance, 1)
                })
        return movements

    def model_schedule_dependencies(self, train_no: str):
        """
        Model how a delay in one train impacts others in the same corridor.
        Uses delays.csv to find historical ripples.
        """
        train_delays = self.delay_db[self.delay_db['train_no'] == int(train_no) if train_no.isdigit() else train_no]
        if train_delays.empty:
            return {"error": "No historical delay data for this train."}
        
        avg_delay = train_delays['delay_min'].mean()
        stations_affected = train_delays['station'].unique().tolist()
        
        # Ripple effect: find other trains sharing these stations
        ripple_potential = self.train_db[
            (self.train_db['origin'].isin(stations_affected)) | 
            (self.train_db['destination'].isin(stations_affected))
        ].head(5) # Limit for summary
        
        return {
            "train_no": train_no,
            "avg_historical_delay": round(avg_delay, 1),
            "critical_stations": stations_affected,
            "ripple_impact_trains": ripple_potential['train_no'].tolist()
        }