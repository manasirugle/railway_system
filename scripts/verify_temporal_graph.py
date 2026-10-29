import sys
import os
from datetime import datetime

# Add the project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.graph.temporal_graph import TemporalRailwayGraph

def main():
    tg = TemporalRailwayGraph()
    
    # Paths
    data_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../data'))
    stations_path = os.path.join(data_dir, 'stations.csv')
    routes_path = os.path.join(data_dir, 'routes.csv')
    trains_path = os.path.join(data_dir, 'trains_full.csv')
    delays_path = os.path.join(data_dir, 'delays.csv')
    
    print("--- 1. Building Temporal Model ---")
    tg.build_temporal_model(stations_path, routes_path, trains_path, delays_path)
    
    print("\n--- 2. Corridor Connectivity Analysis ---")
    corridors = tg.get_corridor_connectivity()
    for corridor, info in corridors.items():
        print(f"{corridor}: {info['status']} ({info.get('distance', 'N/A')})")
        
    print("\n--- 3. Train Movement Pattern (Simulation at 10:30 AM) ---")
    sim_time = datetime(2024, 1, 1, 10, 30, 0)
    movements = tg.get_train_movement_at(sim_time)
    print(f"Simulated {len(movements)} train positions at {sim_time.strftime('%H:%M')}.")
    # Show first 5 movements
    for m in movements[:5]:
        print(f"  Train on {m['from']} -> {m['to']} at {m['progress']*100}% progress ({m['distance_covered']} km)")

    print("\n--- 4. Schedule Dependency Modeling (Train 12176) ---")
    dependency = tg.model_schedule_dependencies("12176")
    print(f"Historical Ripple Effect for Train 12176:")
    print(f"  Avg Delay: {dependency.get('avg_historical_delay')} min")
    print(f"  Critical Stations: {dependency.get('critical_stations')}")
    print(f"  Potentially Impacted Trains: {dependency.get('ripple_impact_trains')}")

if __name__ == "__main__":
    main()
