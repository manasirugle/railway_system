# backend/models/routing.py
import networkx as nx

class RoutingEngine:
    def __init__(self, G, congestion_model=None, delay_model=None):
        self.G    = G
        self.cong = congestion_model
        self.delay = delay_model
        # Multi-objective weights: Alpha (Time), Beta (Delay), Gamma (Congestion)
        self.alpha = 1.0
        self.beta  = 1.5
        self.gamma = 2.0

    def _weight(self, u, v, data):
        time_weight = data.get('base_hrs', 1.0)
        
        # Predicted Delay from cascade model or edge data
        delay_min = data.get('current_delay', 0)
        if self.delay:
            # Simple heuristic: if we have a model, we could use its prediction
            # For dynamic weights in Dijkstra, we'll stick to current or recent cascade results
            pass 
        delay_weight = delay_min / 60.0

        # Congestion from Prophet model
        congestion_index = 0
        if self.cong:
            corridor = f"{u}-{v}"
            # In a real system we'd use current hour forecast, here we use a small penalty
            congestion_index = data.get('congestion_level', 0.1) # 0 to 1 scale

        # Weight = (alpha * Time) + (beta * Delay) + (gamma * Congestion)
        return (self.alpha * time_weight) + (self.beta * delay_weight) + (self.gamma * congestion_index)

    def find_route(self, origin, destination):
        try:
            path      = nx.shortest_path(self.G, origin, destination,
                                          weight=self._weight)
            total_hrs = nx.shortest_path_length(self.G, origin, destination,
                                                 weight=self._weight)
            total_dist = sum(
                self.G[path[i]][path[i+1]].get('distance', 0)
                for i in range(len(path)-1)
            )
            return {
                'path': path, 'total_hours': round(total_hrs, 2),
                'total_distance': round(total_dist, 1),
                'num_stops': len(path)-1, 'status': 'OK'
            }
        except nx.NetworkXNoPath:
            return {'path': [], 'total_hours': None, 'status': 'NO_PATH'}
        except nx.NodeNotFound as e:
            return {'path': [], 'total_hours': None, 'status': f'STATION_NOT_FOUND: {e}'}

    def find_alternatives(self, origin, destination,
                          blocked_station=None, top_k=3):
        G2 = self.G.copy()
        if blocked_station and blocked_station in G2:
            G2.remove_node(blocked_station)
        paths = []
        try:
            for path in nx.shortest_simple_paths(G2, origin, destination,
                                                  weight='base_hrs'):
                total = sum(G2[path[i]][path[i+1]].get('base_hrs', 1)
                            for i in range(len(path)-1))
                delay = sum(G2[path[i]][path[i+1]].get('current_delay', 0)
                            for i in range(len(path)-1))
                dist  = sum(G2[path[i]][path[i+1]].get('distance', 0)
                            for i in range(len(path)-1))
                paths.append({
                    'path':       path,
                    'total_hrs':  round(total, 2),
                    'delay_min':  round(delay, 1),
                    'distance':   round(dist, 1),
                    'num_stops':  len(path)-1,
                    'score':      round(total + delay/60*0.5, 2)
                })
                if len(paths) >= top_k:
                    break
        except Exception:
            pass
        return sorted(paths, key=lambda x: x['score'])


if __name__ == '__main__':
    import sys
    import os
    # Add project root to sys.path
    root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if root_dir not in sys.path:
        sys.path.append(root_dir)
    
    from backend.graph.railway_graph import RailwayGraph
    rg = RailwayGraph()
    G  = rg.build_from_csv('data/stations.csv', 'data/routes.csv')

    re = RoutingEngine(G)

    print('=== Routing Engine Test ===')
    r = re.find_route('NDLS', 'HWH')
    print(f"NDLS → HWH: {r['path']} | {r['total_hours']}h | {r['total_distance']}km")

    r2 = re.find_route('NDLS', 'MAS')
    print(f"NDLS → MAS: {r2['path']} | {r2['total_hours']}h")

    print('\nAlternatives NDLS → HWH (blocking CNB):')
    alts = re.find_alternatives('NDLS', 'HWH', blocked_station='CNB')
    for i, a in enumerate(alts):
        print(f"  Option {i+1}: {a['path']} | score={a['score']}")

    print('\nRouting engine ✅')