from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from contextlib import asynccontextmanager
import joblib, pandas as pd, time, os
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime
from uuid import uuid4
from typing import List, Optional

# ── GLOBAL MODEL INSTANCES ────────────────────────────────────────
rg = delay_m = cong_m = ticket_m = routing = intel = flow_m = None

# ── VULNERABILITY CACHE (computed once at startup) ────────────────
_vuln_scores: dict = {}          # station -> score dict
_vuln_list:   list = []          # sorted list for /vulnerability

# ── TTL CACHE ─────────────────────────────────────────────────────
# Simple dict-based cache: { key: (value, expiry_timestamp) }
_cache: dict = {}

# Local development fallback storage when Firebase/Firestore is unavailable.
_local_sessions: dict = {}


def _local_user_sessions(uid: str):
    return _local_sessions.setdefault(uid, {})


def cache_get(key: str):
    entry = _cache.get(key)
    if entry and time.time() < entry[1]:
        return entry[0]
    return None

def cache_set(key: str, value, ttl_seconds: int):
    _cache[key] = (value, time.time() + ttl_seconds)

import math as _math
import json as _json
from fastapi.responses import JSONResponse as _JSONResponse

# ── NaN-safe JSON ─────────────────────────────────────────────────
# Python's json module raises ValueError on nan/inf by default.
# We replace every non-finite float with 0 so no endpoint ever 500s
# due to bad numeric data coming out of NetworkX or pandas.

def _clean(v, default=0):
    """Replace nan/inf float with a safe default."""
    if isinstance(v, float) and not _math.isfinite(v):
        return default
    return v

def _clean_dict(obj):
    """Recursively sanitize any structure for JSON serialisation."""
    if isinstance(obj, dict):
        return {k: _clean_dict(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_clean_dict(i) for i in obj]
    if isinstance(obj, float) and not _math.isfinite(obj):
        return 0
    # numpy scalars (np.float64 etc.) — convert and check
    try:
        import numpy as np
        if isinstance(obj, (np.floating, np.integer)):
            v = obj.item()
            return 0 if isinstance(v, float) and not _math.isfinite(v) else v
        if isinstance(obj, np.ndarray):
            return _clean_dict(obj.tolist())
    except ImportError:
        pass
    return obj

class _SafeJSONResponse(_JSONResponse):
    """JSONResponse that silently replaces nan/inf instead of crashing."""
    def render(self, content) -> bytes:
        cleaned = _clean_dict(content)
        return _json.dumps(cleaned, allow_nan=False).encode('utf-8')



# TTLs (seconds)
TTL_LIVE_CASCADE  = 30    # matches frontend 30s refresh
TTL_LIVE_DELAYS   = 30    # RailRadar data — 7 stations, expensive
TTL_LIVE_SUMMARY  = 30    # per-station summary
TTL_CONGESTION    = 300   # Prophet forecast — 5 min
TTL_OPERATOR      = 60    # operator briefing — 1 min


@asynccontextmanager
async def lifespan(app: FastAPI):
    global rg, delay_m, cong_m, ticket_m, routing, intel, flow_m
    global _vuln_scores, _vuln_list

    print("Loading models...")
    from backend.graph.temporal_graph        import TemporalRailwayGraph
    from backend.graph.vulnerability         import VulnerabilityAnalyzer
    from backend.models.delay_model          import DelayCascadeModel
    from backend.models.congestion_model     import CongestionModel
    from backend.models.ticket_model         import TicketConfirmationModel
    from backend.models.routing              import RoutingEngine
    from backend.models.passenger_intelligence import PassengerIntelligenceEngine
    from backend.models.passenger_flow         import PassengerFlowModel

    rg      = TemporalRailwayGraph()
    rg.build_temporal_model('data/stations.csv', 'data/routes.csv', 'data/trains_full.csv', 'data/delays.csv')
    G       = rg.G

    delay_m = DelayCascadeModel(G)
    delay_m.model = joblib.load('backend/models/saved/delay_model.pkl')

    cong_m  = CongestionModel()

    ticket_m = TicketConfirmationModel()
    ticket_m.model = joblib.load('backend/models/saved/ticket_model.pkl')

    routing = RoutingEngine(G, cong_m, delay_m)
    flow_m  = PassengerFlowModel(
        pd.read_csv('data/stations.csv').to_dict('records'),
        pd.read_csv('data/routes.csv').to_dict('records')
    )
    intel   = PassengerIntelligenceEngine(delay_m, cong_m, ticket_m, routing)

    # ── Pre-compute vulnerability scores ONCE at startup ──────────
    # Betweenness centrality is O(VE) — never compute this per-request
    print("Pre-computing vulnerability scores...")
    va = VulnerabilityAnalyzer(rg.G)
    raw = va.compute_centrality()
    _vuln_list   = raw
    _vuln_scores = {r['station']: r for r in raw}
    print(f"Vulnerability pre-computed for {len(_vuln_scores)} stations ✅")

    print("All models loaded ✅")
    yield
    print("Shutting down...")


# ── FIREBASE SETUP (LOCAL DEV MODE: auth disabled) ───────────────
# These endpoints are intentionally opened for local development so the app
# can run without Firebase auth or a service account.
from fastapi import Header, Depends

try:
    cred = credentials.Certificate("backend/api/serviceAccountKey.json")
    firebase_admin.initialize_app(cred)
    db = firestore.client()
except Exception:
    db = None

async def get_current_user(authorization: str = Header(None)):
    # Local-only mode: allow every request through without token validation.
    return {"uid": "local-dev-user", "email": "local@gleis.dev", "local_dev": True}

async def check_operator(user: dict = Depends(get_current_user)):
    # Local-only mode: all users are treated as operators.
    return user


# ── PYDANTIC MODELS ───────────────────────────────────────────────
class Message(BaseModel):
    role: str
    content: str
    timestamp: datetime = datetime.now()

class Session(BaseModel):
    session_id: str
    title: str = "New Chat Session"
    created_at: datetime = datetime.now()
    last_message_at: datetime = datetime.now()

class ChatReq(BaseModel):
    query: str
    session_id: str
    mode: str = 'passenger'

class SessionResponse(BaseModel):
    session_id: str
    title: str

class ChatResponse(BaseModel):
    response: str
    session_id: str
    title: str
    mode: str

class TicketReq(BaseModel):
    wl:          int
    days:        int  = 60
    cls:         str  = '3AC'
    quota:       str  = 'General'
    peak:        int  = 0
    train_type:  str  = 'Express'
    distance:    int  = 500
    travel_time: int  = 10
    seats:       int  = 100
    passengers:  int  = 1

class BriefingReq(BaseModel):
    origin:       str
    destination:  str
    date:         str = '2025-12-25'
    travel_class: str = '3AC'
    wl_number:    int = None
    season_peak:  int = 0

class BookingGuidanceReq(BaseModel):
    origin:       str
    destination:  str
    date:         str = '2025-12-25'
    travel_class: str = '3AC'
    wl_number:    int = None


# ── APP ───────────────────────────────────────────────────────────
app = FastAPI(title='Railway AI API', version='1.0', lifespan=lifespan, default_response_class=_SafeJSONResponse)
app.add_middleware(CORSMiddleware, allow_origins=['*'],
                   allow_methods=['*'], allow_headers=['*'])


# ── HEALTH ────────────────────────────────────────────────────────
@app.get('/health')
async def health():
    return {
        'status': 'ok',
        'graph_nodes': rg.G.number_of_nodes(),
        'graph_edges': rg.G.number_of_edges(),
    }


# ── GRAPH ─────────────────────────────────────────────────────────
@app.get('/graph')
async def get_graph():
    raw = rg.to_geojson()
    return _clean_dict(raw)
@app.get('/graph/stations')
async def get_stations():
    rows = []
    for node, data in rg.G.nodes(data=True):
        lat = _clean(data.get('lat', 0), 0)
        lon = _clean(data.get('lon', 0), 0)
        if lat == 0 and lon == 0:
            continue  # skip stations with no coordinates — unusable on map
        rows.append({
            'id':       node,
            'name':     data.get('name', node),
            'lat':      lat,
            'lon':      lon,
            'zone':     data.get('zone', '') or '',
            'capacity': int(_clean(data.get('capacity', 300), 300)),
            'risk_level':          _vuln_scores.get(node, {}).get('risk_level', 'LOW'),
            'vulnerability_score': _clean(_vuln_scores.get(node, {}).get('vulnerability_score', 0), 0),
        })
    return rows

TTL_TEMPORAL_MOVE = 10   # train positions refresh every 10s
TTL_TEMPORAL_CORR = 300  # corridor connectivity is static — 5 min
 
@app.get('/graph/temporal/movements')
async def temporal_movements():
    """
    Current simulated train positions on the network.
    Returns list of {from, to, progress, distance_covered}.
    Uses pseudo-temporal progress based on current time so dots move.
    """
    cached = cache_get('temporal_movements')
    if cached:
        return cached
    result = await run_in_threadpool(rg.get_train_movement_at, datetime.now())
    result = _clean_dict(result)
    cache_set('temporal_movements', result, TTL_TEMPORAL_MOVE)
    return result
 
@app.get('/graph/temporal/corridors')
async def temporal_corridors():
    """
    North/South/East/West corridor connectivity derived from graph shortest paths.
    Returns dict of "Region -> Region": {status, distance, hubs}.
    """
    cached = cache_get('temporal_corridors')
    if cached:
        return cached
    result = await run_in_threadpool(rg.get_corridor_connectivity)
    cache_set('temporal_corridors', result, TTL_TEMPORAL_CORR)
    return result

# ── DELAY CASCADE ─────────────────────────────────────────────────
@app.get('/cascade/vulnerable')
async def vulnerable_routes():
    return delay_m.get_vulnerable_routes(top_n=8)

@app.get('/cascade/{station}/{delay}')
async def cascade(station: str, delay: int):
    station = station.upper()
    if station not in rg.G.nodes:
        raise HTTPException(404, f'Station {station} not found')
    result = delay_m.simulate_cascade(station, delay)
    return {
        'origin':            station,
        'initial_delay':     delay,
        'affected_stations': len(result),
        'cascade':           result,
    }


# ── CONGESTION ────────────────────────────────────────────────────
@app.get('/congestion')
async def congestion():
    cached = cache_get('congestion_all')
    if cached:
        return cached

    corridors = ['NDLS-CNB','NDLS-ADI','CNB-HWH','ADI-CSTM','SC-MAS','NDLS-JP','HWH-MAS']
    result = cong_m.get_congestion_hotspots(corridors, top_n=6)
    cache_set('congestion_all', result, TTL_CONGESTION)
    return result

@app.get('/congestion/{corridor}')
async def congestion_corridor(corridor: str):
    key = f'congestion_{corridor}'
    cached = cache_get(key)
    if cached:
        return cached
    result = cong_m.forecast_next_24h(corridor)
    cache_set(key, result, TTL_CONGESTION)
    return result


# ── TICKET ────────────────────────────────────────────────────────

def _days_ahead_factor(days: int, wl: int) -> float:
    """
    Training CSV had days_ahead=244 for every row (zero variance) so the
    XGBoost model assigns it near-zero weight.  Apply a calibrated post-hoc
    sigmoid multiplier derived from real WL movement patterns.
    Centred at 1.0 around 60 days — the standard advance-booking window.
      7d  -> ~0.55    (very little WL movement left)
     15d  -> ~0.68
     30d  -> ~0.83
     60d  -> ~1.00
     90d  -> ~1.10
    120d  -> ~1.15
    """
    import math
    factor = 0.35 + 0.80 / (1 + math.exp(-0.045 * (days - 30)))
    if wl > 100 and days < 30:   # high WL + very little time = extra penalty
        factor *= 0.75
    return round(factor, 4)

@app.post('/ticket/predict')
async def ticket_predict(req: TicketReq):
    base = ticket_m.predict_confirmation(
        wl_number         = req.wl,
        days_ahead        = req.days,
        travel_class      = req.cls,
        quota             = req.quota,
        season_peak       = req.peak,
        train_type        = req.train_type,
        travel_distance   = req.distance,
        travel_time       = req.travel_time,
        seat_availability = req.seats,
        num_passengers    = req.passengers,
    )

    # Apply days-ahead multiplier on top of model score
    raw_prob = base.get("confirmation_probability", 50)
    factor   = _days_ahead_factor(req.days, req.wl)
    adjusted = round(min(99, max(1, raw_prob * factor)), 1)
    base["confirmation_probability"] = adjusted

    # Regenerate message to match adjusted probability
    if adjusted >= 75:
        base["message"] = f"High confirmation chance. Booking {req.days} days ahead gives good WL movement time."
    elif adjusted >= 50:
        base["message"] = f"Moderate chance — {'consider booking earlier for better odds.' if req.days < 30 else 'probability may improve as travel date approaches.'}"
    elif adjusted >= 25:
        base["message"] = f"Lower chance — {'very little time for WL movement at ' + str(req.days) + ' days out.' if req.days < 15 else 'high WL position limits movement window.'}"
    else:
        base["message"] = f"Confirmation unlikely — {'book immediately or try a different class/train.' if req.days < 7 else 'high WL with limited movement window.'}"

    return base

@app.get('/ticket/alternatives/{origin}/{destination}')
async def ticket_alternatives(origin: str, destination: str, wl: int = 45):
    try:
        trains_df = pd.read_csv('data/trains_full.csv')
        mask = (trains_df['origin'].str.upper() == origin.upper()) & \
               (trains_df['destination'].str.upper() == destination.upper())
        route_trains = trains_df[mask].head(5).to_dict('records')
    except Exception:
        route_trains = [
            {'train_no': '12301', 'name': 'Rajdhani Express'},
            {'train_no': '12381', 'name': 'Poorva Express'},
            {'train_no': '13005', 'name': 'Amritsar Mail'},
        ]
    return ticket_m.suggest_alternatives(route_trains, wl_cutoff=wl)


# ── VULNERABILITY ─────────────────────────────────────────────────
@app.get('/vulnerability')
async def vulnerability():
    # Returns pre-computed list — instant, no recompute
    return _vuln_list[:10]

@app.get('/vulnerability/{station}')
async def station_vulnerability(station: str):
    from backend.graph.vulnerability import VulnerabilityAnalyzer
    va = VulnerabilityAnalyzer(rg.G)
    return va.simulate_station_removal(station.upper())


# ── ROUTING ───────────────────────────────────────────────────────
@app.get('/route/{origin}/{destination}')
async def find_route(origin: str, destination: str):
    return routing.find_route(origin.upper(), destination.upper())

@app.get('/route/{origin}/{destination}/alternatives')
async def find_alternatives(origin: str, destination: str, blocked: str = None):
    return routing.find_alternatives(
        origin.upper(), destination.upper(),
        blocked_station=blocked.upper() if blocked else None
    )


# ── PASSENGER INTELLIGENCE ────────────────────────────────────────
@app.post('/intelligence/briefing')
async def travel_briefing(req: BriefingReq):
    return intel.get_travel_briefing(
        req.origin.upper(), req.destination.upper(),
        req.date, req.travel_class,
        req.wl_number, req.season_peak
    )

@app.get('/intelligence/operator')
async def operator_briefing(user: dict = Depends(check_operator)):
    cached = cache_get('operator_briefing')
    if cached:
        return cached
    result = intel.get_operator_briefing()
    cache_set('operator_briefing', result, TTL_OPERATOR)
    return result

@app.get('/intelligence/status')
async def system_status(user: dict = Depends(get_current_user)):
    """Public system health for all authenticated users (Passengers + Operators)."""
    cached = cache_get('operator_briefing')
    if cached:
        return {
            'network_health': cached.get('network_health', 'NORMAL'),
            'timestamp': cached.get('timestamp')
        }
    result = intel.get_operator_briefing()
    cache_set('operator_briefing', result, TTL_OPERATOR)
    return {
        'network_health': result.get('network_health', 'NORMAL'),
        'timestamp': result.get('timestamp')
    }

@app.get('/intelligence/adjustments')
async def travel_adjustments(user: dict = Depends(check_operator)):
    return intel.recommend_operational_adjustments()

@app.post('/intelligence/booking')
async def smart_booking(req: BookingGuidanceReq):
    return intel.get_smart_booking_guidance(
        req.origin.upper(), req.destination.upper(),
        req.date, req.travel_class, req.wl_number
    )


# ── PASSENGER FLOW ────────────────────────────────────────────────
@app.get('/crowd/{station_id}')
async def crowd(station_id: str, date: str = None, hour: int = None):
    from datetime import date as date_type
    d = date or str(date_type.today())
    h = hour if hour is not None else datetime.now().hour
    return flow_m.get_station_crowd(station_id.upper(), d, h)


# ── CHAT SESSION MANAGEMENT ───────────────────────────────────────
@app.post('/chat/session', response_model=SessionResponse)
async def create_session(user: dict = Depends(get_current_user)):
    uid = user['uid']
    session_id = str(uuid4())
    session_data = {
        'session_id': session_id,
        'title': 'New Chat Session',
        'created_at': datetime.now(),
        'last_message_at': datetime.now(),
        'messages': []
    }
    if db is not None:
        db.collection('users').document(uid) \
          .collection('sessions').document(session_id).set(session_data)
    else:
        _local_user_sessions(uid)[session_id] = session_data
    return {'session_id': session_id, 'title': session_data['title']}

@app.get('/chat/sessions', response_model=List[SessionResponse])
async def list_sessions(user: dict = Depends(get_current_user)):
    uid = user['uid']
    if db is not None:
        sessions_ref = db.collection('users').document(uid) \
                         .collection('sessions') \
                         .order_by('last_message_at', direction=firestore.Query.DESCENDING)
        sessions = []
        for doc in sessions_ref.stream():
            data = doc.to_dict()
            sessions.append({'session_id': data['session_id'], 'title': data['title']})
        return sessions

    sessions = _local_user_sessions(uid)
    return [
        {'session_id': sid, 'title': s.get('title', 'New Chat Session')}
        for sid, s in sorted(sessions.items(), key=lambda kv: kv[1].get('last_message_at', datetime.min), reverse=True)
    ]

@app.delete('/chat/session/{session_id}')
async def delete_session(session_id: str, user: dict = Depends(get_current_user)):
    uid = user['uid']
    if db is not None:
        messages_ref = db.collection('users').document(uid) \
                         .collection('sessions').document(session_id).collection('messages')
        for msg in messages_ref.stream():
            msg.reference.delete()
        db.collection('users').document(uid) \
          .collection('sessions').document(session_id).delete()
    else:
        _local_user_sessions(uid).pop(session_id, None)
    return {"status": "deleted"}

@app.delete('/chat/session/{session_id}/messages')
async def clear_session_messages(session_id: str, user: dict = Depends(get_current_user)):
    uid = user['uid']
    if db is not None:
        messages_ref = db.collection('users').document(uid) \
                         .collection('sessions').document(session_id).collection('messages')
        for msg in messages_ref.stream():
            msg.reference.delete()
        db.collection('users').document(uid) \
          .collection('sessions').document(session_id).update({'title': 'New Chat Session'})
    else:
        sessions = _local_user_sessions(uid)
        if session_id in sessions:
            sessions[session_id]['title'] = 'New Chat Session'
            sessions[session_id]['messages'] = []
    return {"status": "cleared"}

@app.get('/chat/session/{session_id}/messages', response_model=List[dict])
async def get_session_messages(session_id: str, user: dict = Depends(get_current_user)):
    uid = user['uid']
    if db is not None:
        messages_ref = db.collection('users').document(uid) \
                         .collection('sessions').document(session_id) \
                         .collection('messages') \
                         .order_by('timestamp', direction=firestore.Query.ASCENDING)
        messages = []
        for doc in messages_ref.stream():
            data = doc.to_dict()
            messages.append({
                "role": data['role'],
                "content": data['content'],
                "timestamp": data['timestamp'].isoformat()
                             if hasattr(data['timestamp'], 'isoformat')
                             else str(data['timestamp'])
            })
        return messages

    sessions = _local_user_sessions(uid)
    session = sessions.get(session_id)
    if not session:
        return []
    return session.get('messages', [])


# ── CHAT ─────────────────────────────────────────────────────────
# run_in_threadpool moves blocking Groq/OpenRouter/Firestore calls
# off the async event loop so other requests aren't blocked
@app.post('/chat', response_model=ChatResponse)
async def chat(req: ChatReq, user: dict = Depends(get_current_user)):
    uid = user['uid']
    if db is None:
        role = 'operator'
    else:
        role = 'operator' if db.collection('authorized_operators').document(user.get('email')).get().exists else 'passenger'

    def _blocking_chat():
        from backend.assistant.router    import route_query
        from backend.assistant.tools     import execute_tool
        from backend.assistant.generator import generate_response, generate_chat_title

        if db is None:
            sessions = _local_user_sessions(uid)
            session = sessions.get(req.session_id)
            if not session:
                raise HTTPException(404, "Session not found")
            title = session.get('title', 'New Chat Session')
            history = session.get('messages', [])[-5:]
            if req.mode == 'operator' and role != 'operator':
                return {'response': "I'm sorry, operator mode is restricted to authorised personnel. How can I help you as a passenger?", 'session_id': req.session_id, 'title': title, 'mode': 'passenger'}
            router_res = route_query(req.query)
            tool = router_res.get("tool", "unknown")
            params = router_res.get("params", {})
            if tool == "general_info" or tool == "unknown" or not tool:
                answer = generate_response(req.query, tool or "unknown", {}, history=history)
            else:
                result = execute_tool(tool, params)
                answer = generate_response(req.query, tool, result, history=history)
            if title == 'New Chat Session':
                title = generate_chat_title(req.query)
                session['title'] = title
            now = datetime.now()
            session.setdefault('messages', []).append({'role': 'user', 'content': req.query, 'timestamp': now.isoformat()})
            session['messages'].append({'role': 'assistant', 'content': answer, 'timestamp': now.isoformat()})
            session['last_message_at'] = now
            return {'response': answer, 'session_id': req.session_id, 'title': title, 'mode': req.mode}

        session_ref = db.collection('users').document(uid) \
                        .collection('sessions').document(req.session_id)
        session_doc = session_ref.get()
        if not session_doc.exists:
            raise HTTPException(404, "Session not found")

        # RBAC check for operator mode
        if req.mode == 'operator' and role != 'operator':
            return {'response': "I'm sorry, operator mode is restricted to authorised personnel. How can I help you as a passenger?", 'session_id': req.session_id, 'title': session_doc.to_dict().get('title', 'New Chat'), 'mode': 'passenger'}

        # Last 5 messages for context
        raw_history = list(
            session_ref.collection('messages')
                       .order_by('timestamp', direction=firestore.Query.DESCENDING)
                       .limit(5)
                       .stream()
        )
        raw_history.reverse()
        history = [{"role": m.to_dict()['role'], "content": m.to_dict()['content']}
                   for m in raw_history]

        router_res = route_query(req.query)
        tool   = router_res.get("tool", "unknown")
        params = router_res.get("params", {})

        if tool == "general_info" or tool == "unknown" or not tool:
            # For general info or unknown, we don't call an API, let the LLM handle it from internal knowledge
            answer = generate_response(req.query, tool or "unknown", {}, history=history)
        else:
            result = execute_tool(tool, params)
            answer = generate_response(req.query, tool, result, history=history)

        title = session_doc.to_dict().get('title', 'New Chat Session')
        if title == 'New Chat Session':
            title = generate_chat_title(req.query)
            session_ref.update({'title': title})

        timestamp = datetime.now()
        session_ref.collection('messages').add({'role': 'user',      'content': req.query, 'timestamp': timestamp})
        session_ref.collection('messages').add({'role': 'assistant', 'content': answer,    'timestamp': datetime.now()})
        session_ref.update({'last_message_at': datetime.now()})

        return {'response': answer, 'session_id': req.session_id, 'title': title, 'mode': req.mode}

    return await run_in_threadpool(_blocking_chat)


# ── LIVE DATA — RailRadar ─────────────────────────────────────────
from backend.live.rail_api import (
    get_station_live,
    get_delayed_trains_at_station,
    get_all_live_delays,
    get_station_board_summary,
)

@app.get('/live/station/{code}')
async def live_station_board(code: str):
    return get_station_live(code.upper())

@app.get('/live/station/{code}/summary')
async def live_station_summary(code: str):
    key    = f'summary_{code.upper()}'
    cached = cache_get(key)
    if cached:
        return cached
    result = get_station_board_summary(code.upper())
    cache_set(key, result, TTL_LIVE_SUMMARY)
    return result

@app.get('/live/delays')
async def live_delays():
    # Single cache key covers all 7 stations — fetched together
    cached = cache_get('live_delays_all')
    if cached:
        return cached
    result = get_all_live_delays()
    cache_set('live_delays_all', result, TTL_LIVE_DELAYS)
    return result

@app.get('/live/delays/{station}')
async def live_delays_station(station: str):
    # Re-use the already-cached full delays, just filter — zero extra API calls
    cached = cache_get('live_delays_all')
    if cached:
        all_alerts = cached.get("alerts", [])
    else:
        full = get_all_live_delays()
        cache_set('live_delays_all', full, TTL_LIVE_DELAYS)
        all_alerts = full.get("alerts", [])

    filtered = [a for a in all_alerts if a.get("at_station", "").upper() == station.upper()]
    return {
        "station": station.upper(),
        "delayed": len(filtered),
        "alerts":  filtered,
    }

@app.get('/live/cascade')
async def live_cascade():
    """
    STAR ENDPOINT — real delays → ML cascade model → live predictions.
    Cached for 30s: the cascade simulations are expensive (NetworkX on 203 nodes × N delayed trains).
    """
    cached = cache_get('live_cascade')
    if cached:
        return cached

    live   = get_all_live_delays(stations=["NDLS", "CNB"])
    # Also update the shared delays cache so /live/delays benefits too
    cache_set('live_delays_all', live, TTL_LIVE_DELAYS)

    result = []
    for alert in live.get("alerts", []):
        station = alert.get("at_station", "").upper()
        delay   = alert.get("delay_minutes", 0)
        if station and station in rg.G.nodes and delay > 0:
            cascade_result = delay_m.simulate_cascade(station, delay)
            result.append({
                "train":             alert["train_name"],
                "train_number":      alert["train_number"],
                "trigger_station":   station,
                "trigger_delay_min": delay,
                "severity":          alert["severity"],
                "affected_stations": len(cascade_result),
                "cascade":           cascade_result,
            })

    response = {
        "fetched_at":      live["fetched_at"],
        "active_cascades": len(result),
        "all_delays":      live["alerts"],
        "cascades":        result,
    }
    cache_set('live_cascade', response, TTL_LIVE_CASCADE)
    return response


# ── STATIC FRONTEND ───────────────────────────────────────────────
frontend_dir = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "frontend"
)
app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")