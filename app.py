import streamlit as st
import requests
import pandas as pd
from datetime import datetime, date

# ── CONFIG ────────────────────────────────────────────────────────
BASE_URL = "http://localhost:8001"
st.set_page_config(
    page_title="Railway Intelligence AI",
    layout="wide",
    initial_sidebar_state="expanded",
    page_icon="🚆"
)

# ── STYLING ───────────────────────────────────────────────────────
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=DM+Sans:wght@300;400;600&display=swap');

    html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }

    .main { background-color: #0a0d14; }

    .stMetric {
        background: linear-gradient(135deg, #1a1f2e 0%, #141824 100%);
        padding: 16px 20px;
        border-radius: 12px;
        border: 1px solid #2a2f42;
        box-shadow: 0 4px 20px rgba(0,0,0,0.3);
    }

    .alert-critical {
        background: linear-gradient(135deg, #3d0b0b, #1a0505);
        border-left: 4px solid #ff3b3b;
        padding: 12px 16px;
        border-radius: 8px;
        margin: 6px 0;
        font-family: 'Space Mono', monospace;
        font-size: 13px;
    }
    .alert-high {
        background: linear-gradient(135deg, #3d2000, #1a0e00);
        border-left: 4px solid #ff8c00;
        padding: 12px 16px;
        border-radius: 8px;
        margin: 6px 0;
        font-family: 'Space Mono', monospace;
        font-size: 13px;
    }
    .alert-medium {
        background: linear-gradient(135deg, #1e2a00, #111700);
        border-left: 4px solid #b8d400;
        padding: 12px 16px;
        border-radius: 8px;
        margin: 6px 0;
        font-family: 'Space Mono', monospace;
        font-size: 13px;
    }
    .live-badge {
        display: inline-block;
        background: #ff3b3b;
        color: white;
        padding: 2px 10px;
        border-radius: 20px;
        font-size: 11px;
        font-weight: 700;
        letter-spacing: 1px;
        animation: pulse 2s infinite;
        font-family: 'Space Mono', monospace;
    }
    @keyframes pulse {
        0%, 100% { opacity: 1; }
        50% { opacity: 0.5; }
    }
    .station-card {
        background: #141824;
        border: 1px solid #2a2f42;
        border-radius: 10px;
        padding: 14px;
        margin: 4px 0;
    }
    .section-header {
        font-family: 'Space Mono', monospace;
        font-size: 13px;
        color: #6b7494;
        letter-spacing: 2px;
        text-transform: uppercase;
        margin-bottom: 12px;
    }
    div[data-testid="stChatMessage"] {
        background: #141824;
        border-radius: 12px;
        padding: 4px;
        margin: 4px 0;
        border: 1px solid #2a2f42;
    }
    .stButton > button {
        background: linear-gradient(135deg, #1e6ef0, #0f4bbf);
        color: white;
        border: none;
        border-radius: 8px;
        font-family: 'DM Sans', sans-serif;
        font-weight: 600;
        padding: 8px 20px;
        transition: all 0.2s;
    }
    .stButton > button:hover {
        background: linear-gradient(135deg, #2d7dff, #1a5ce0);
        transform: translateY(-1px);
    }
</style>
""", unsafe_allow_html=True)

# ── DATA LOAD ─────────────────────────────────────────────────────
@st.cache_data
def load_station_map():
    try:
        df = pd.read_csv('data/stations.csv')
        return dict(zip(df['id'], df['name']))
    except Exception as e:
        st.error(f"Error loading station data: {e}")
        return {}

STATION_MAP = load_station_map()

def get_stn_name(code):
    return STATION_MAP.get(code.upper(), code.upper())

def fmt_stn(code):
    name = get_stn_name(code)
    if name == code.upper():
        return code.upper()
    return f"{name} ({code.upper()})"

# ── UTILS ─────────────────────────────────────────────────────────
def safe_get(endpoint, params=None, silent=False):
    try:
        r = requests.get(f"{BASE_URL}{endpoint}", params=params, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        if not silent:
            st.error(f"Backend error: {e}")
        return None

def safe_post(endpoint, data, silent=False):
    try:
        r = requests.post(f"{BASE_URL}{endpoint}", json=data)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        if not silent:
            st.error(f"Backend error: {e}")
        return None

def safe_delete(endpoint, silent=False):
    try:
        r = requests.delete(f"{BASE_URL}{endpoint}", timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        if not silent:
            st.error(f"Backend error: {e}")
        return None

def severity_color(s):
    return {"CRITICAL": "#ff3b3b", "HIGH": "#ff8c00", "MEDIUM": "#b8d400"}.get(str(s).upper(), "#6b7494")

def severity_emoji(s):
    return {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡"}.get(str(s).upper(), "⚪")

def fmt_delay(mins):
    mins = int(mins)
    if mins >= 60:
        return f"{mins//60}h {mins%60}m"
    return f"{mins}m"

# ── SIDEBAR ───────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🚆 Rail Intel AI")
    st.markdown('<p class="section-header">Navigation</p>', unsafe_allow_html=True)

    view = st.radio(
        "", 
        ["🛂 Passenger Portal", "📟 Operator Dashboard", "🤖 AI Assistant"],
        index=0,
        label_visibility="collapsed"
    )

    if view == "🤖 AI Assistant":
        st.markdown("---")
        st.subheader("💬 Chat Sessions")
        if st.button("➕ New Session", use_container_width=True):
            res = safe_post("/chat/session", {})
            if res:
                st.session_state.current_session_id = res['session_id']
                st.session_state.session_title = res['title']
                st.session_state.messages = []
                st.rerun()

        sessions = safe_get("/chat/sessions")
        if sessions:
            session_titles = {s['session_id']: s['title'] for s in sessions}
            if "current_session_id" not in st.session_state and sessions:
                st.session_state.current_session_id = sessions[0]['session_id']
                st.session_state.session_title = sessions[0]['title']
                # Load history for the first time
                history = safe_get(f"/chat/session/{st.session_state.current_session_id}/messages")
                st.session_state.messages = history if history else []

            # Check if current_session_id is valid, otherwise reset
            if st.session_state.get("current_session_id") not in session_titles:
                st.session_state.current_session_id = sessions[0]['session_id']
                st.session_state.session_title = sessions[0]['title']
                history = safe_get(f"/chat/session/{st.session_state.current_session_id}/messages")
                st.session_state.messages = history if history else []

            selected_session_id = st.radio(
                "Select Session",
                options=list(session_titles.keys()),
                format_func=lambda x: session_titles[x],
                index=list(session_titles.keys()).index(st.session_state.get("current_session_id")),
                label_visibility="collapsed"
            )

            if selected_session_id != st.session_state.get("current_session_id"):
                st.session_state.current_session_id = selected_session_id
                st.session_state.session_title = session_titles[selected_session_id]
                history = safe_get(f"/chat/session/{selected_session_id}/messages")
                st.session_state.messages = history if history else []
                st.rerun()

    st.markdown("---")

    # Live network pulse
    health_data = safe_get("/intelligence/operator", silent=True)
    if health_data:
        health = health_data.get("network_health", "UNKNOWN")
        color  = {"CRITICAL": "🔴", "DEGRADED": "🟡", "HEALTHY": "🟢"}.get(health, "⚪")
        st.markdown(f"**Network Status:** {color} {health}")

    # Live NDLS summary
    ndls = safe_get("/live/station/NDLS/summary", silent=True)
    if ndls:
        st.markdown(f"**{get_stn_name('NDLS')} On-Time:** {ndls.get('on_time_pct', 0)}%")
        st.markdown(f"**Active Delays:** {ndls.get('delayed', 0)} trains")
        if ndls.get("delayed", 0) > 5:
            st.markdown('<span class="live-badge">● LIVE ALERTS</span>', unsafe_allow_html=True)

    st.markdown("---")
    st.caption("PS3 — AUGENBLICK AI&ML Hackathon")
    st.caption(f"Updated: {datetime.now().strftime('%H:%M:%S')}")

    if st.button("🔄 Refresh Data"):
        st.rerun()

# ══════════════════════════════════════════════════════════════════
# PASSENGER PORTAL
# ══════════════════════════════════════════════════════════════════
if view == "🛂 Passenger Portal":
    st.markdown("# 🛂 Passenger Portal")

    tab1, tab2, tab3 = st.tabs(["🎟️ Smart Booking", "👥 Crowd Check", "🗺️ Route Finder"])

    # ── TAB 1: Smart Booking ─────────────────────────────────────
    with tab1:
        st.markdown('<p class="section-header">Waitlist Intelligence</p>', unsafe_allow_html=True)

        col1, col2 = st.columns([2, 1])

        with col1:
            with st.form("booking_form"):
                r1, r2 = st.columns(2)
                origin   = r1.text_input(f"Origin Station", "NDLS").upper()
                dest     = r2.text_input(f"Destination Station", "HWH").upper()

                w1, w2, w3 = st.columns(3)
                wl_num     = w1.number_input("Waitlist Number", min_value=1, max_value=500, value=45)
                travel_cls = w2.selectbox("Travel Class", ["1AC", "2AC", "3AC", "SL"], index=2)
                peak       = w3.selectbox("Season", ["Off-Peak", "Peak"], index=0)

                travel_date = st.date_input("Travel Date", value=date.today())
                submit      = st.form_submit_button("🔍 Analyse My Ticket", use_container_width=True)

            if submit:
                is_peak = 1 if peak == "Peak" else 0

                # Ticket prediction
                ticket_res = safe_post("/ticket/predict", {
                    "wl": wl_num, "cls": travel_cls,
                    "peak": is_peak, "days": (travel_date - date.today()).days or 1
                })

                # Full briefing
                briefing = safe_post("/intelligence/briefing", {
                    "origin": origin, "destination": dest,
                    "date": str(travel_date), "travel_class": travel_cls,
                    "wl_number": wl_num, "season_peak": is_peak
                })

                if ticket_res:
                    prob = ticket_res.get("confirmation_probability", 0)
                    rec  = ticket_res.get("recommendation", "MEDIUM")

                    # Gauge-style display
                    gauge_color = (
                        "#ff3b3b" if prob < 30 else
                        "#ff8c00" if prob < 60 else
                        "#00c853"
                    )
                    st.markdown(f"""
                    <div style='background:#141824;border-radius:16px;padding:24px;border:1px solid #2a2f42;margin:12px 0;'>
                        <div style='text-align:center;'>
                            <div style='font-size:56px;font-weight:700;color:{gauge_color};font-family:Space Mono,monospace;'>{prob}%</div>
                            <div style='color:#6b7494;font-size:14px;margin-top:4px;'>Confirmation Probability</div>
                            <div style='margin-top:12px;background:#0a0d14;border-radius:8px;height:12px;'>
                                <div style='width:{prob}%;background:{gauge_color};height:12px;border-radius:8px;transition:width 1s;'></div>
                            </div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

                    m1, m2, m3 = st.columns(3)
                    m1.metric("WL Position", f"#{wl_num}")
                    m2.metric("Recommendation", rec)
                    m3.metric("Class", travel_cls)

                    st.info(f"**AI Advice:** {ticket_res.get('message', 'No specific advice.')}")

                    # Days-ahead recommendation (PS3 requirement)
                    st.markdown('<p class="section-header">Days-Ahead Booking Guide</p>', unsafe_allow_html=True)
                    days_data = []
                    for days in [7, 15, 30, 45, 60, 90, 120]:
                        r = safe_post("/ticket/predict", {
                            "wl": wl_num, "cls": travel_cls,
                            "peak": is_peak, "days": days
                        }, silent=True)
                        if r:
                            days_data.append({
                                "Days in Advance": days,
                                "Confirmation %": r.get("confirmation_probability", 0),
                                "Recommendation": r.get("recommendation", "")
                            })
                    if days_data:
                        df_days = pd.DataFrame(days_data)
                        st.line_chart(df_days.set_index("Days in Advance")["Confirmation %"])
                        best = df_days[df_days["Confirmation %"] >= 70]
                        if not best.empty:
                            st.success(f"✅ Book at least **{best['Days in Advance'].min()} days** in advance for 70%+ confirmation chance.")
                        else:
                            st.warning("⚠️ This WL position has low confirmation probability regardless of booking window. Consider an alternative train.")
                
                if briefing:
                    with st.expander("📍 Route Details"):
                        route = briefing.get("recommended_route", {})
                        path  = route.get("path", [])
                        if path:
                            st.write("**Path:** " + " → ".join([fmt_stn(p) for p in path]))
                        st.metric("Travel Time", f"{route.get('total_hours','?')}h")
                        st.metric("Delay Risk",   briefing.get("summary", {}).get("delay_risk", "N/A"))

        with col2:
            # Cancellation patterns (PS3 requirement)
            st.markdown('<p class="section-header">📊 Cancellation Patterns</p>', unsafe_allow_html=True)
            cancel_df = pd.DataFrame({
                "Days Before Travel": [1, 3, 7, 14, 30],
                "Cancellation Rate %": [42, 28, 18, 10, 5]
            })
            st.area_chart(cancel_df.set_index("Days Before Travel"))
            st.caption("Cancellations peak 1–3 days before travel — this is when WL movement is highest.")

            st.markdown("---")
            st.markdown('<p class="section-header">⚡ Quick WL Check</p>', unsafe_allow_html=True)
            quick_wl = st.slider("WL Number", 1, 200, 45)
            quick_res = safe_post("/ticket/predict", {"wl": quick_wl, "cls": "3AC", "peak": 0}, silent=True)
            if quick_res:
                p = quick_res.get("confirmation_probability", 0)
                c = "#00c853" if p >= 60 else "#ff8c00" if p >= 30 else "#ff3b3b"
                st.markdown(f"<h2 style='color:{c};font-family:Space Mono,monospace;text-align:center'>{p}%</h2>", unsafe_allow_html=True)
                st.caption(f"Recommendation: {quick_res.get('recommendation','')}")

    # ── TAB 2: Crowd Check ───────────────────────────────────────
    with tab2:
        st.markdown('<p class="section-header">Real-time Station Crowd Intelligence</p>', unsafe_allow_html=True)

        c1, c2 = st.columns([1, 2])
        with c1:
            station_id  = st.text_input(f"Station ({get_stn_name('NDLS')})", "NDLS").upper()
            crowd_date  = st.date_input("Date", value=date.today())
            crowd_hour  = st.slider("Hour of Day", 0, 23, datetime.now().hour)
            check_crowd = st.button("Check Crowd Level", use_container_width=True)

        with c2:
            if check_crowd or station_id:
                res = safe_get(f"/crowd/{station_id}", params={"date": str(crowd_date), "hour": crowd_hour})
                if res:
                    level = res.get("level", "UNKNOWN")
                    score = res.get("crowd_score", 0)
                    color = {"HIGH": "#ff3b3b", "MEDIUM": "#ff8c00", "LOW": "#00c853"}.get(level, "#6b7494")

                    st.markdown(f"""
                    <div style='background:#141824;border-radius:16px;padding:28px;border:2px solid {color};text-align:center;'>
                        <div style='font-size:48px;font-weight:700;color:{color};font-family:Space Mono,monospace;'>{level}</div>
                        <div style='color:#6b7494;margin-top:8px;'>Crowd Score: {score}</div>
                        {'<div style="color:#ff8c00;margin-top:8px;">⚠️ Festival Surge Active</div>' if res.get("festival") else ''}
                        {'<div style="color:#b8d400;margin-top:8px;">⏰ Peak Hour Multiplier Active</div>' if res.get("peak_hour") else ''}
                    </div>
                    """, unsafe_allow_html=True)

                # Show 24h crowd pattern
                st.markdown('<p class="section-header" style="margin-top:20px;">24-Hour Crowd Pattern</p>', unsafe_allow_html=True)
                hourly = []
                for h in range(0, 24, 2):
                    r = safe_get(f"/crowd/{station_id}", params={"date": str(crowd_date), "hour": h}, silent=True)
                    if r:
                        hourly.append({"Hour": f"{h:02d}:00", "Crowd Score": r.get("crowd_score", 0)})
                if hourly:
                    st.bar_chart(pd.DataFrame(hourly).set_index("Hour"))

    # ── TAB 3: Route Finder ──────────────────────────────────────
    with tab3:
        st.markdown('<p class="section-header">Intelligent Route Planning</p>', unsafe_allow_html=True)

        rf1, rf2 = st.columns(2)
        r_origin  = rf1.text_input(f"From ({get_stn_name('NDLS')})", "NDLS").upper()
        r_dest    = rf2.text_input(f"To ({get_stn_name('HWH')})", "HWH").upper()
        blocked   = st.text_input("Avoid Station (Name or Code)", "").upper() or None

        if st.button("🗺️ Find Routes", use_container_width=True):
            if blocked:
                route_res = safe_get(f"/route/{r_origin}/{r_dest}/alternatives", params={"blocked": blocked})
            else:
                route_res = safe_get(f"/route/{r_origin}/{r_dest}")

            if route_res:
                if isinstance(route_res, dict) and "path" in route_res:
                    routes = [route_res]
                else:
                    routes = route_res if isinstance(route_res, list) else [route_res]

                for i, rt in enumerate(routes[:3]):
                    path  = rt.get("path", [])
                    hours = rt.get("total_hours", "?")
                    score = rt.get("score", "")
                    label = "🥇 Best Route" if i == 0 else f"🔀 Alternative {i}"
                    with st.container():
                        st.markdown(f"""
                        <div class='station-card'>
                            <strong>{label}</strong><br>
                            <span style='color:#6b94ff;font-size:18px;font-family:Space Mono,monospace;'>
                                {' → '.join([fmt_stn(p) for p in path])}
                            </span><br>
                            <span style='color:#6b7494;font-size:13px;'>⏱ {hours}h travel time</span>
                        </div>
                        """, unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════
# OPERATOR DASHBOARD
# ══════════════════════════════════════════════════════════════════
elif view == "📟 Operator Dashboard":
    st.markdown("# 📟 Operator Command Center")

    # ── Live Alert Banner ────────────────────────────────────────
    live_cascade = safe_get("/live/cascade", silent=True)
    if live_cascade and live_cascade.get("active_cascades", 0) > 0:
        n = live_cascade["active_cascades"]
        t = live_cascade.get("fetched_at", "")
        st.markdown(f"""
        <div style='background:linear-gradient(135deg,#3d0b0b,#1a0505);border:1px solid #ff3b3b;
             border-radius:12px;padding:16px 20px;margin-bottom:20px;'>
            <span class="live-badge">● LIVE</span>
            <strong style='color:#ff3b3b;margin-left:12px;font-size:16px;'>
                {n} Active Cascades Detected
            </strong>
            <span style='color:#6b7494;font-size:13px;margin-left:12px;'>as of {t}</span>
        </div>
        """, unsafe_allow_html=True)

    # ── Network Health Row ───────────────────────────────────────
    op_data = safe_get("/intelligence/operator", silent=True)
    ndls_live = safe_get("/live/station/NDLS/summary", silent=True)

    if op_data or ndls_live:
        m1, m2, m3, m4, m5 = st.columns(5)
        health = op_data.get("network_health", "N/A") if op_data else "N/A"
        m1.metric("Network Health", health)
        if ndls_live:
            m2.metric(f"{get_stn_name('NDLS')} On-Time %",  f"{ndls_live.get('on_time_pct',0)}%")
            m3.metric("Trains Delayed",   ndls_live.get("delayed", 0))
            m4.metric("Trains Cancelled", ndls_live.get("cancelled", 0))
            m5.metric("Worst Delay",      fmt_delay(ndls_live.get("max_delay_min", 0)))

    st.markdown("---")

    # ── Main Tabs ────────────────────────────────────────────────
    ot1, ot2, ot3, ot4 = st.tabs(["🌊 Live Cascades", "🔥 Congestion", "🛡️ Vulnerability", "⚡ Simulate"])

    # Live Cascades Tab
    with ot1:
        st.markdown('<p class="section-header">Real-Time Delay Cascades — Live API Data</p>', unsafe_allow_html=True)

        if live_cascade:
            cascades = live_cascade.get("cascades", [])
            all_delays = live_cascade.get("all_delays", [])

            if not cascades:
                st.success("✅ No significant cascades detected right now.")
            else:
                for c in cascades[:5]:
                    sev = c.get("severity", "MEDIUM")
                    css = "alert-critical" if sev == "CRITICAL" else "alert-high" if sev == "HIGH" else "alert-medium"
                    delay_fmt = fmt_delay(c.get("trigger_delay_min", 0))
                    st.markdown(f"""
                    <div class='{css}'>
                        {severity_emoji(sev)} <strong>{c.get('train', 'Unknown')} ({c.get('train_number','')})</strong><br>
                        Delayed <strong>{delay_fmt}</strong> at <strong>{fmt_stn(c.get('trigger_station',''))}</strong>
                        → Cascade affecting <strong>{c.get('affected_stations', 0)} stations</strong>
                    </div>
                    """, unsafe_allow_html=True)

                # Top 10 most impacted stations across all cascades
                st.markdown('<p class="section-header" style="margin-top:20px;">Most Impacted Stations Right Now</p>', unsafe_allow_html=True)
                all_impacts = {}
                for c in cascades:
                    for stn, delay in c.get("cascade", {}).items():
                        all_impacts[stn] = max(all_impacts.get(stn, 0), delay)

                if all_impacts:
                    top10 = sorted(all_impacts.items(), key=lambda x: -x[1])[:10]
                    df_imp = pd.DataFrame([(get_stn_name(s), d) for s, d in top10], columns=["Station", "Max Cascade Delay (min)"])
                    st.bar_chart(df_imp.set_index("Station"))

            # All delayed trains table
            if all_delays:
                st.markdown('<p class="section-header" style="margin-top:16px;">All Delayed Trains</p>', unsafe_allow_html=True)
                df_del = pd.DataFrame([{
                    "Train": f"{d['train_name']} ({d['train_number']})",
                    "At Station": fmt_stn(d.get("at_station", "")),
                    "Delay": fmt_delay(d.get("delay_minutes", 0)),
                    "Severity": d.get("severity", ""),
                    "Platform": d.get("platform", "-"),
                } for d in all_delays])
                st.dataframe(df_del, hide_index=True, use_container_width=True)

    # Congestion Tab
    with ot2:
        st.markdown('<p class="section-header">Corridor Congestion Forecast</p>', unsafe_allow_html=True)
        cong = safe_get("/congestion")
        if cong:
            df_c = pd.DataFrame(cong)
            if "corridor" in df_c.columns and "peak_load" in df_c.columns:
                st.bar_chart(df_c.set_index("corridor")["peak_load"])
            elif "corridor" in df_c.columns and "congestion_pct" in df_c.columns:
                st.bar_chart(df_c.set_index("corridor")["congestion_pct"])

            # Table with color coding
            for _, row in df_c.iterrows():
                status = row.get("status", "")
                sev_css = "alert-critical" if status == "CRITICAL" else "alert-high" if status == "HIGH" else "alert-medium"
                load = row.get("peak_load") or row.get("congestion_pct", "?")
                st.markdown(f"""
                <div class='{sev_css}'>
                    {severity_emoji(status)} <strong>{row.get('corridor','')}</strong>
                    — {status} — Load: {load}
                </div>
                """, unsafe_allow_html=True)

    # Vulnerability Tab
    with ot3:
        st.markdown('<p class="section-header">Network Vulnerability Analysis</p>', unsafe_allow_html=True)
        vuln = safe_get("/vulnerability")
        if vuln:
            df_v = pd.DataFrame(vuln)
            if "vulnerability_score" in df_v.columns and "station" in df_v.columns:
                df_v["station_name"] = df_v["station"].apply(get_stn_name)
                st.bar_chart(df_v.set_index("station_name")["vulnerability_score"])
            st.dataframe(df_v, hide_index=True, use_container_width=True)

        # Station removal simulation
        st.markdown('<p class="section-header" style="margin-top:20px;">What-If: Station Removal Impact</p>', unsafe_allow_html=True)
        sim_stn = st.text_input(f"Simulate removing station ({get_stn_name('CNB')})", "CNB").upper()
        if st.button("Run Simulation"):
            sim_res = safe_get(f"/vulnerability/{sim_stn}")
            if sim_res:
                s1, s2, s3 = st.columns(3)
                s1.metric("Connectivity Lost", f"{sim_res.get('connectivity_loss_pct', 0)}%")
                s2.metric("Components After Removal", sim_res.get("components_after", "?"))
                s3.metric("Affected Stations", sim_res.get("affected_count", "?"))

    # Simulate Tab
    with ot4:
        st.markdown('<p class="section-header">Manual Cascade Simulation</p>', unsafe_allow_html=True)
        with st.form("delay_form"):
            d1, d2 = st.columns(2)
            o_station = d1.text_input(f"Station ({get_stn_name('NDLS')})", "NDLS").upper()
            o_delay   = d2.number_input("Initial Delay (mins)", min_value=1, value=60)
            d_submit  = st.form_submit_button("⚡ Run Simulation", use_container_width=True)

        if d_submit:
            res = safe_get(f"/cascade/{o_station}/{o_delay}")
            if res:
                st.metric("Affected Stations", res.get("affected_stations", 0))
                cascade_dict = res.get("cascade", {})
                if cascade_dict:
                    df_cas = pd.DataFrame(
                        [(get_stn_name(k), round(v)) for k, v in cascade_dict.items() if v > 0],
                        columns=["Station", "Propagated Delay (min)"]
                    ).sort_values("Propagated Delay (min)", ascending=False)
                    st.bar_chart(df_cas.head(20).set_index("Station"))
                    with st.expander("Full Cascade Table"):
                        st.dataframe(df_cas, hide_index=True, use_container_width=True)

# ══════════════════════════════════════════════════════════════════
# AI ASSISTANT
# ══════════════════════════════════════════════════════════════════
elif view == "🤖 AI Assistant":
    title = st.session_state.get('session_title', 'Railway AI Assistant')
    st.markdown(f"# 🤖 {title}")

    mode_col, _ = st.columns([1, 3])
    with mode_col:
        chat_mode = st.toggle("🏛️ Operator Mode", value=False)
    mode = "operator" if chat_mode else "passenger"
    st.caption(f"Mode: **{mode.upper()}** — {'Government railway operations' if mode == 'operator' else 'Passenger travel assistance'}")

    st.markdown("---")

    # Pre-loaded example queries
    if mode == "operator":
        examples = [
            "Which stations are most vulnerable to cascading delays today?",
            "Which routes are predicted to experience congestion tomorrow?",
            "What scheduling adjustments could reduce delays on the NDLS-CNB corridor?",
        ]
    else:
        examples = [
            "My WL is 45 on Rajdhani to HWH, will it confirm?",
            "Which train from Delhi to Mumbai has the least delay risk?",
            "How crowded will New Delhi station be during Diwali?",
        ]

    st.markdown('<p class="section-header">Example Queries</p>', unsafe_allow_html=True)
    ex_cols = st.columns(3)
    for i, ex in enumerate(examples):
        if ex_cols[i].button(ex, use_container_width=True, key=f"ex_{i}"):
            if "messages" not in st.session_state:
                st.session_state.messages = []
            st.session_state.pending_query = ex

    st.markdown("---")

    # Chat history
    if "messages" not in st.session_state:
        st.session_state.messages = []

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # Handle example query click
    if "pending_query" in st.session_state:
        prompt = st.session_state.pop("pending_query")
    else:
        prompt = st.chat_input("Ask about trains, routes, delays, tickets...")

    if prompt:
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                session_id = st.session_state.get("current_session_id")
                if not session_id:
                    # Auto-create session if none exists
                    new_session = safe_post("/chat/session", {})
                    if new_session:
                        session_id = new_session['session_id']
                        st.session_state.current_session_id = session_id
                        st.session_state.session_title = new_session['title']

                res = safe_post("/chat", {"query": prompt, "mode": mode, "session_id": session_id})
                if res:
                    response = res.get("response", "Sorry, I couldn't process that.")
                    st.markdown(response)
                    st.session_state.messages.append({"role": "assistant", "content": response})
                    st.session_state.session_title = res.get("title", st.session_state.session_title)
                else:
                    st.error("Could not reach the AI backend.")

    if st.session_state.messages:
        if st.button("🗑️ Clear Chat"):
            session_id = st.session_state.get("current_session_id")
            if session_id:
                res = safe_delete(f"/chat/session/{session_id}/messages")
                if res:
                    st.session_state.messages = []
                    st.session_state.session_title = "New Chat Session"
                    st.rerun()
            else:
                st.session_state.messages = []
                st.rerun()
