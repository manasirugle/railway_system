import networkx as nx
import pandas as pd
import json
from datetime import datetime


class RailwayGraph:
    def __init__(self):
        self.G = nx.DiGraph()
        self.delay_log = {}  # {edge: [timestamps, delays]}

    def build_from_csv(self, stations_path, routes_path):
        stations = pd.read_csv(stations_path)
        routes   = pd.read_csv(routes_path)

        # Add station nodes
        for _, s in stations.iterrows():
            self.G.add_node(s['id'],
                name=s['name'], lat=s['lat'], lon=s['lon'],
                zone=s['zone'], capacity=s['capacity'],
                current_load=0, vulnerability_score=0.0,
                delay_risk='low'
            )

        # Add track edges (bidirectional)
        for _, r in routes.iterrows():
            attrs = dict(
                distance=r['distance'], base_hrs=r['travel_hrs'],
                capacity=r['capacity'],  current_delay=0,
                trains=[], delay_history=[]
            )
            self.G.add_edge(r['from'], r['to'], **attrs)
            self.G.add_edge(r['to'], r['from'], **attrs)  # reverse

        print(f'Graph built: {self.G.number_of_nodes()} nodes, {self.G.number_of_edges()} edges')
        return self.G

    def update_delay(self, from_station, to_station, delay_min):
        '''Update edge delay and log for time-series analysis'''
        if self.G.has_edge(from_station, to_station):
            self.G[from_station][to_station]['current_delay'] = delay_min
            key = f'{from_station}-{to_station}'
            if key not in self.delay_log:
                self.delay_log[key] = {'times': [], 'delays': []}
            self.delay_log[key]['times'].append(datetime.now().isoformat())
            self.delay_log[key]['delays'].append(delay_min)

    def get_delayed_weight(self, u, v, data):
        '''Edge weight = base travel time + current delay'''
        return data['base_hrs'] + data['current_delay'] / 60.0

    def shortest_path(self, source, target):
        return nx.shortest_path(self.G, source, target,
                                weight=self.get_delayed_weight)

    def to_geojson(self):
        '''Export for Folium map rendering'''
        features = []
        for n, d in self.G.nodes(data=True):
            features.append({'type':'Feature',
                'geometry': {'type':'Point','coordinates':[d['lon'],d['lat']]},
                'properties': {**d, 'id': n}})
        for u, v, d in self.G.edges(data=True):
            nu, nv = self.G.nodes[u], self.G.nodes[v]
            features.append({'type':'Feature',
                'geometry': {'type':'LineString',
                    'coordinates':[[nu['lon'],nu['lat']],[nv['lon'],nv['lat']]]},
                'properties': {**d, 'from': u, 'to': v}})
        return {'type':'FeatureCollection','features':features}


# Usage
rg = RailwayGraph()
G  = rg.build_from_csv('data/stations.csv', 'data/routes.csv')
