import sys
import os
sys.path.append(os.getcwd())

from backend.graph.temporal_graph import TemporalRailwayGraph
from backend.graph.vulnerability import VulnerabilityAnalyzer
import pandas as pd

def test():
    print("Initializing TemporalRailwayGraph...")
    try:
        rg = TemporalRailwayGraph()
        rg.build_temporal_model('data/stations.csv', 'data/routes.csv', 'data/trains_full.csv', 'data/delays.csv')
        print(f"Graph nodes: {rg.G.number_of_nodes()}")
        
        print("Pre-computing vulnerability scores...")
        va = VulnerabilityAnalyzer(rg.G)
        raw = va.compute_centrality()
        _vuln_scores = {r['station']: r for r in raw}
        print(f"Pre-computed scores for {len(_vuln_scores)} stations")
        
        print("Testing get_stations logic...")
        rows = []
        for node, data in rg.G.nodes(data=True):
            rows.append({
                'id':       node,
                'name':     data.get('name', node),
                'lat':      data.get('lat', 0),
                'lon':      data.get('lon', 0),
                'zone':     data.get('zone', ''),
                'capacity': data.get('capacity', 300),
                'risk_level':          _vuln_scores.get(node, {}).get('risk_level', 'LOW'),
                'vulnerability_score': _vuln_scores.get(node, {}).get('vulnerability_score', 0),
            })
        print(f"Successfully processed {len(rows)} stations.")
        print("Sample station:", rows[0] if rows else "None")
        
    except Exception as e:
        import traceback
        print("ERROR OCCURRED:")
        traceback.print_exc()

if __name__ == "__main__":
    test()
