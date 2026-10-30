import streamlit as st
import streamlit.components.v1 as components
import requests
import pandas as pd
import plotly.express as px
import math
from datetime import datetime, timezone
from html import escape

# ==========================================
# CONFIG
# ==========================================

st.set_page_config(
    page_title="PLAN RADAR X",
    page_icon="✈️",
    layout="wide",
    initial_sidebar_state="expanded"
)

API = "https://api.adsb.lol/v2"

DEFAULT_LAT = 23.8103
DEFAULT_LON = 90.4125
DEFAULT_RADIUS = 250

# ==========================================
# DESIGN
# ==========================================

st.markdown("""
<style>
.stApp {
    background: #050b10;
    color: #d9ffe9;
}
[data-testid="stSidebar"] {
    background: #09151b;
    border-right: 1px solid #174b38;
}
h1, h2, h3 {
    color: #50ff9a !important;
}
p, label {
    color: #c2d7ce;
}
div[data-testid="stMetric"] {
    background: #0c1c1b;
    border: 1px solid #205a42;
    padding: 14px;
    border-radius: 10px;
}
.stButton button {
    background: #087c49;
    color: white;
    border: 1px solid #25e88b;
    border-radius: 8px;
    font-weight: bold;
}
.stButton button:hover {
    background: #0ca65f;
    color: white;
}
.radar-title {
    color: #52ff9b;
    font-size: 36px;
    font-weight: 900;
    letter-spacing: 4px;
}
.radar-subtitle {
    color: #7da995;
    font-size: 12px;
    letter-spacing: 3px;
}
</style>
""", unsafe_allow_html=True)

# ==========================================
# SESSION STATE
# ==========================================

defaults = {
    "aircraft": [],
    "api_total": 0,
    "last_update": None,
    "api_error": None,
    "search_results": [],
    "selected_icao": None,
    "watchlist": [],          # নতুন ফিচার: ওয়াচলিস্ট
    "flight_history": {}      # নতুন ফিচার: ফ্লাইট ট্রেইল/হিস্ট্রি হিস্টোরি
}

for key, value in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value

# ==========================================
# API REQUEST
# ==========================================

def api_request(endpoint):
    try:
        response = requests.get(
            API + endpoint,
            headers={"User-Agent": "PLAN-RADAR-X/3.0"},
            timeout=(10, 25)
        )

        if response.status_code == 429:
            return None, "API rate limit reached. Please wait."

        response.raise_for_status()
        return response.json(), None

    except requests.exceptions.Timeout:
        return None, "API connection timed out."

    except requests.exceptions.ConnectionError:
        return None, "Could not connect to adsb.lol."

    except requests.exceptions.HTTPError as e:
        return None, f"HTTP error: {e}"

    except (requests.exceptions.RequestException, ValueError) as e:
        return None, str(e)

# ==========================================
# NORMALIZE AIRCRAFT
# ==========================================

def normalize_aircraft(items):
    result = []

    for plane in items or []:
        try:
            lat = float(plane.get("lat"))
            lon = float(plane.get("lon"))

            if not (-90 <= lat <= 90):
                continue

            if not (-180 <= lon <= 180):
                continue

        except (TypeError, ValueError):
            continue

        icao = str(plane.get("hex") or "").upper()
        lat_val = lat
        lon_val = lon
        alt_val = plane.get("alt_baro")
        gs_val = plane.get("gs")

        # ফ্লাইট হিস্ট্রি ট্র্যাক করার লজিক (নতুন ফিচার)
        if icao:
            if icao not in st.session_state.flight_history:
                st.session_state.flight_history[icao] = []
            
            history_list = st.session_state.flight_history[icao]
            # নতুন পয়েন্ট যোগ করা (সর্বোচ্চ ২০টি পয়েন্ট জমা থাকবে)
            point = {"Latitude": lat_val, "Longitude": lon_val, "Altitude": alt_val, "Speed": gs_val}
            if not history_list or history_list[-1]["Latitude"] != lat_val or history_list[-1]["Longitude"] != lon_val:
                history_list.append(point)
                if len(history_list) > 20:
                    history_list.pop(0)

        result.append({
            "ICAO": icao,
            "Callsign": str(plane.get("flight") or "").strip(),
            "Registration": plane.get("r"),
            "Aircraft Type": plane.get("t"),
            "Latitude": lat_val,
            "Longitude": lon_val,
            "Altitude (ft)": alt_val,
            "Ground Speed (knots)": gs_val,
            "Heading": plane.get("track"),
            "Vertical Rate": plane.get("baro_rate"),
            "Squawk": plane.get("squawk"),
            "On Ground": alt_val == "ground",
            "Category": plane.get("category"),
            "Messages": plane.get("messages"),
            "Seen (seconds)": plane.get("seen"),
            "Source": plane.get("type")
        })

    return result

# ==========================================
# FETCH AIRCRAFT
# ==========================================

def fetch_area(lat, lon, radius):
    endpoint = f"/lat/{lat}/lon/{lon}/dist/{radius}"

    data, error = api_request(endpoint)

    if error:
        return None, 0, error

    if not isinstance(data, dict):
        return None, 0, "Unexpected API response."

    raw = data.get("ac") or []
    total = data.get("total", len(raw))

    return normalize_aircraft(raw), total, None

# ==========================================
# FLIGHT SEARCH
# ==========================================

def search_flight(query):
    query = query.strip().upper()

    if not query:
        return [], "Enter a flight number or ICAO."

    endpoint = "/callsign/" + requests.utils.quote(
        query, safe=""
    )

    data, error = api_request(endpoint)

    if error:
        return [], error

    results = []

    if isinstance(data, dict):
        results = normalize_aircraft(data.get("ac", []))

    if not results and len(query) == 6:
        data, error = api_request("/hex/" + query)

        if error:
            return [], error

        if isinstance(data, dict):
            results = normalize_aircraft(data.get("ac", []))

    return results, None

# ==========================================
# DISTANCE AND BEARING
# ==========================================

def distance_bearing(lat1, lon1, lat2, lon2):
    rlat1 = math.radians(lat1)
    rlat2 = math.radians(lat2)

    dlat = rlat2 - rlat1
    dlon = math.radians(lon2 - lon1)

    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(rlat1) * math.cos(rlat2)
        * math.sin(dlon / 2) ** 2
    )

    distance_km = 6371 * 2 * math.atan2(
        math.sqrt(a),
        math.sqrt(max(0, 1 - a))
    )

    y = math.sin(dlon) * math.cos(rlat2)

    x = (
        math.cos(rlat1) * math.sin(rlat2)
        - math.sin(rlat1) * math.cos(rlat2)
        * math.cos(dlon)
    )

    bearing = (
        math.degrees(math.atan2(y, x)) + 360
    ) % 360

    return distance_km / 1.852, bearing

# ==========================================
# PREPARE TARGETS
# ==========================================

def prepare_targets(aircraft, center_lat, center_lon):
    targets = []

    for plane in aircraft:
        distance, bearing = distance_bearing(
            center_lat,
            center_lon,
            plane["Latitude"],
            plane["Longitude"]
        )

        item = plane.copy()
        item["Distance (NM)"] = round(distance, 1)
        item["Direction (°)"] = round(bearing, 1)

        targets.append(item)

    return targets

# ==========================================
# SMOOTH CSS RADAR
# ==========================================

def create_radar_html(targets, radius, selected_icao):

    dots = []

    for plane in targets:
        distance = plane["Distance (NM)"]
        bearing = plane["Direction (°)"]

        if radius <= 0:
            continue

        angle = math.radians(bearing)
        scale = min(distance / radius, 1.0)

        x = 50 + math.sin(angle) * scale * 45
        y = 50 - math.cos(angle) * scale * 45

        callsign = (
            plane["Callsign"]
            or plane["ICAO"]
            or "UNKNOWN"
        )

        safe_title = escape(
            f"{callsign} | ICAO: {plane['ICAO']} | {distance} NM",
            quote=True
        )

        selected = plane["ICAO"] == selected_icao

        color = "#ffcf48" if selected else "#ffffff"
        size = "13px" if selected else "9px"

        dots.append(
            f'<div class="aircraft-dot" title="{safe_title}" '
            f'style="left:{x:.3f}%;top:{y:.3f}%;'
            f'background:{color};width:{size};height:{size};">'
            f'</div>'
        )

    dots_html = "\n".join(dots)

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
    <meta name="viewport" content="width=device-width">
    <style>

    * {{
        box-sizing: border-box;
    }}

    html, body {{
        margin: 0;
        padding: 0;
        background: #050b10;
        overflow: hidden;
        font-family: Arial, sans-serif;
    }}

    .radar-stage {{
        width: 100%;
        height: 640px;
        display: flex;
        align-items: center;
        justify-content: center;
        background:
        radial-gradient(
            ellipse at center,
            #0b2119 0%,
            #06130e 58%,
            #050b10 100%
        );
    }}

    .radar {{
        width: min(88vw, 610px);
        aspect-ratio: 1 / 1;
        position: relative;
        overflow: hidden;
        border-radius: 50%;
        border: 2px solid #2b8055;

        background:
        radial-gradient(
            circle,
            transparent 19.5%,
            rgba(31,112,72,.65) 19.8%,
            transparent 20.2%
        ),
        radial-gradient(
            circle,
            transparent 39.5%,
            rgba(31,112,72,.65) 39.8%,
            transparent 40.2%
        ),
        radial-gradient(
            circle,
            transparent 59.5%,
            rgba(31,112,72,.65) 59.8%,
            transparent 60.2%
        ),
        radial-gradient(
            circle,
            transparent 79.5%,
            rgba(31,112,72,.65) 79.8%,
            transparent 80.2%
        ),
        radial-gradient(
            circle,
            transparent 99%,
            #2b8055 99.5%,
            transparent 100%
        ),
        radial-gradient(
            circle at center,
            #0b2418 0%,
            #06140f 72%,
            #04100c 100%
        );

        box-shadow:
        0 0 22px rgba(27,255,130,.18),
        inset 0 0 28px rgba(27,255,130,.10);
    }}

    .cross {{
        position: absolute;
        background: rgba(47,133,87,.55);
    }}

    .horizontal {{
        width: 100%;
        height: 1px;
        left: 0;
        top: 50%;
    }}

    .vertical {{
        width: 1px;
        height: 100%;
        left: 50%;
        top: 0;
    }}

    .sweep {{
        position: absolute;
        inset: 0;
        border-radius: 50%;

        background: conic-gradient(
            from 0deg,
            rgba(45,255,139,0.00) 0deg,
            rgba(45,255,139,0.02) 8deg,
            rgba(45,255,139,0.07) 19deg,
            rgba(45,255,139,0.23) 28deg,
            rgba(45,255,139,0.00) 35deg,
            rgba(45,255,139,0.00) 360deg
        );

        animation: radar-spin 4s linear infinite;
        transform-origin: center;
        will-change: transform;
        pointer-events: none;
    }}

    .sweep-line {{
        position: absolute;
        left: 50%;
        top: 0;
        width: 2px;
        height: 50%;

        background: linear-gradient(
            to bottom,
            rgba(90,255,160,.95),
            rgba(90,255,160,.12)
        );

        transform-origin: bottom center;
        animation: radar-spin 4s linear infinite;

        box-shadow: 0 0 9px rgba(57,255,145,.8);
        pointer-events: none;
    }}

    @keyframes radar-spin {{
        from {{
            transform: rotate(0deg);
        }}
        to {{
            transform: rotate(360deg);
        }}
    }}

    .aircraft-dot {{
        position: absolute;
        transform: translate(-50%, -50%);
        border-radius: 50%;
        border: 2px solid #39ff91;
        box-shadow:
            0 0 9px #39ff91,
            0 0 17px rgba(57,255,145,.45);
        z-index: 5;
    }}

    .center {{
        position: absolute;
        left: 50%;
        top: 50%;
        width: 13px;
        height: 13px;
        transform: translate(-50%, -50%);
        border-radius: 50%;
        background: white;
        border: 2px solid #39ff91;
        box-shadow: 0 0 12px #39ff91;
        z-index: 8;
    }}

    .radar-label {{
        position: absolute;
        color: rgba(103,255,170,.65);
        font-size: 10px;
        letter-spacing: 1px;
        z-index: 2;
    }}

    .north {{
        top: 8px;
        left: 50%;
        transform: translateX(-50%);
    }}

    .east {{
        right: 9px;
        top: 50%;
        transform: translateY(-50%);
    }}

    .south {{
        bottom: 8px;
        left: 50%;
        transform: translateX(-50%);
    }}

    .west {{
        left: 9px;
        top: 50%;
        transform: translateY(-50%);
    }}

    .radar-footer {{
        position: absolute;
        bottom: 15px;
        left: 50%;
        transform: translateX(-50%);
        color: #69c994;
        font-size: 10px;
        letter-spacing: 2px;
        white-space: nowrap;
        z-index: 10;
    }}

    </style>
    </head>

    <body>
        <div class="radar-stage">
            <div class="radar">

                <div class="cross horizontal"></div>
                <div class="cross vertical"></div>

                <div class="radar-label north">N</div>
                <div class="radar-label east">E</div>
                <div class="radar-label south">S</div>
                <div class="radar-label west">W</div>

                <div class="sweep"></div>
                <div class="sweep-line"></div>

                {dots_html}

                <div class="center"></div>

                <div class="radar-footer">
                    360° LIVE VISUAL SWEEP
                </div>

            </div>
        </div>
    </body>
    </html>
    """

# ==========================================
# AIRCRAFT DETAILS & CHARTS (নতুন ফিচার সহ)
# ==========================================

def show_aircraft_details(plane):

    callsign = (
        plane["Callsign"]
        or plane["ICAO"]
        or "UNKNOWN"
    )

    st.markdown("---")
    col_title, col_btn = st.columns([3, 1])
    with col_title:
        st.markdown(f"## ✈ {callsign}")
        st.caption("SELECTED AIRCRAFT · FLIGHT INFORMATION")
    
    with col_btn:
        icao = plane["ICAO"]
        if icao in st.session_state.watchlist:
            if st.button("❌ Remove Watchlist"):
                st.session_state.watchlist.remove(icao)
                st.rerun()
        else:
            if st.button("⭐ Add Watchlist"):
                st.session_state.watchlist.append(icao)
                st.rerun()

    a, b, c, d = st.columns(4)

    a.metric("ICAO ADDRESS", plane["ICAO"] or "N/A")
    b.metric("AIRCRAFT TYPE", plane["Aircraft Type"] or "Unknown")

    altitude = plane["Altitude (ft)"]
    speed = plane["Ground Speed (knots)"]

    c.metric(
        "ALTITUDE",
        str(altitude) if altitude is not None else "N/A"
    )

    d.metric(
        "GROUND SPEED",
        f"{speed} kt" if speed is not None else "N/A"
    )

    # উচ্চতা ও গতির গ্রাফিক্যাল অ্যানালিসিস (নতুন ফিচার)
    history = st.session_state.flight_history.get(plane["ICAO"], [])
    if len(history) > 1:
        st.markdown("### 📈 FLIGHT PERFORMANCE CHARTS (ALTITUDE & SPEED)")
        df_history = pd.DataFrame(history)
        
        # ফিল্টার আউট নান ভ্যালুস
        df_history = df_history.dropna(subset=["Altitude"])
        if not df_history.empty:
            fig_alt = px.line(df_history, y="Altitude", title="Altitude History (ft)", markers=True)
            fig_alt.update_layout(paper_bgcolor="#050b10", plot_bgcolor="#0c1c1b", font_color="#d9ffe9")
            st.plotly_chart(fig_alt, use_container_width=True)

    identity = {
        "Callsign": plane["Callsign"],
        "ICAO": plane["ICAO"],
        "Registration": plane["Registration"],
        "Aircraft Type": plane["Aircraft Type"],
        "Category": plane["Category"],
        "Squawk": plane["Squawk"]
    }

    position = {
        "Latitude": plane["Latitude"],
        "Longitude": plane["Longitude"],
        "Distance from radar (NM)": plane["Distance (NM)"],
        "Direction (degrees)": plane["Direction (°)"],
        "Heading": plane["Heading"]
    }

    status = {
        "Altitude (ft)": plane["Altitude (ft)"],
        "Ground Speed (knots)": plane["Ground Speed (knots)"],
        "Vertical Rate": plane["Vertical Rate"],
        "On Ground": plane["On Ground"],
        "Messages": plane["Messages"],
        "Seen (seconds ago)": plane["Seen (seconds)"],
        "Data Source": plane["Source"]
    }

    left, right = st.columns(2)

    with left:
        st.markdown("### AIRCRAFT IDENTITY")
        st.dataframe(
            pd.DataFrame(
                list(identity.items()),
                columns=["Field", "Value"]
            ),
            use_container_width=True,
            hide_index=True
        )

        st.markdown("### FLIGHT POSITION")
        st.dataframe(
            pd.DataFrame(
                list(position.items()),
                columns=["Field", "Value"]
            ),
            use_container_width=True,
            hide_index=True
        )

    with right:
        st.markdown("### FLIGHT STATUS")
        st.dataframe(
            pd.DataFrame(
                list(status.items()),
                columns=["Field", "Value"]
            ),
            use_container_width=True,
            hide_index=True
        )

    st.info(
        "Only information supplied by the ADS-B data provider "
        "can be displayed. Missing fields may appear as N/A."
    )

# ==========================================
# HEADER
# ==========================================

st.markdown(
    '<div class="radar-title">✈ PLAN RADAR X</div>',
    unsafe_allow_html=True
)

st.markdown(
    '<div class="radar-subtitle">'
    'ADVANCED AIRCRAFT DETECTION & TRACKING SYSTEM'
    '</div>',
    unsafe_allow_html=True
)

st.divider()

# ==========================================
# SIDEBAR
# ==========================================

st.sidebar.markdown("## ✈ PLAN RADAR X")

page = st.sidebar.radio(
    "SYSTEM NAVIGATION",
    [
        "Radar Scanner",
        "Aircraft Map",
        "Flight Search",
        "Aircraft Database",
        "Watchlist",          # নতুন মেনু অপশন
        "System Information"
    ]
)

st.sidebar.divider()
st.sidebar.markdown("### RADAR SETTINGS")

center_lat = st.sidebar.number_input(
    "Center Latitude",
    value=DEFAULT_LAT,
    min_value=-90.0,
    max_value=90.0,
    format="%.4f"
)

center_lon = st.sidebar.number_input(
    "Center Longitude",
    value=DEFAULT_LON,
    min_value=-180.0,
    max_value=180.0,
    format="%.4f"
)

radius = st.sidebar.slider(
    "Detection Radius (NM)",
    min_value=10,
    max_value=250,
    value=DEFAULT_RADIUS,
    step=10
)

st.sidebar.caption("Default center: Dhaka, Bangladesh")

st.sidebar.divider()

refresh = st.sidebar.button(
    "⟳ SCAN AIRCRAFT NOW",
    use_container_width=True
)

# ==========================================
# FETCH DATA
# ==========================================

if refresh or st.session_state.last_update is None:

    with st.spinner("Scanning aircraft network..."):

        aircraft, api_total, error = fetch_area(
            center_lat,
            center_lon,
            radius
        )

    if aircraft is not None:

        st.session_state.aircraft = aircraft
        st.session_state.api_total = api_total
        st.session_state.last_update = datetime.now(timezone.utc)
        st.session_state.api_error = None

        available_ids = {
            p["ICAO"] for p in aircraft
        }

        if st.session_state.selected_icao not in available_ids:
            st.session_state.selected_icao = None

    else:
        st.session_state.api_error = error

# ==========================================
# STATUS
# ==========================================

if st.session_state.api_error:

    st.error(st.session_state.api_error)

    if st.session_state.last_update:
        st.warning("Showing previously received data.")

elif st.session_state.last_update:
    st.success("Aircraft data received successfully.")

if st.session_state.last_update:

    st.caption(
        "Last scan: "
        + st.session_state.last_update.strftime(
            "%Y-%m-%d %H:%M:%S UTC"
        )
    )

# ==========================================
# PREPARE DATA
# ==========================================

aircraft = st.session_state.aircraft

targets = prepare_targets(
    aircraft,
    center_lat,
    center_lon
)

radar_targets = [
    p for p in targets
    if p["Distance (NM)"] <= radius
]

airborne_count = sum(
    1 for p in aircraft
    if not p["On Ground"]
)

# ==========================================
# METRICS
# ==========================================

c1, c2, c3, c4 = st.columns(4)

c1.metric("API AIRCRAFT", st.session_state.api_total)
c2.metric("VALID AIRCRAFT", len(aircraft))
c3.metric("RADAR TARGETS", len(radar_targets))
c4.metric("AIRBORNE", airborne_count)

st.divider()

# ==========================================
# RADAR SCANNER
# ==========================================

if page == "Radar Scanner":

    st.subheader("◉ 360° ROTATING RADAR")

    st.caption(
        "The radar sweep rotates continuously using browser CSS animation. "
        "Aircraft data updates when you scan."
    )

    if radar_targets:

        radar_html = create_radar_html(
            radar_targets,
            radius,
            st.session_state.selected_icao
        )

        components.html(
            radar_html,
            height=650,
            scrolling=False
        )

        st.markdown("### SELECT AIRCRAFT")

        options = list(range(len(radar_targets)))
        selected_index = 0

        for i, plane in enumerate(radar_targets):
            if plane["ICAO"] == st.session_state.selected_icao:
                selected_index = i
                break

        picker_index = st.selectbox(
            "Choose a detected aircraft",
            options,
            index=selected_index,
            format_func=lambda i: (
                (
                    radar_targets[i]["Callsign"]
                    or radar_targets[i]["ICAO"]
                    or "UNKNOWN"
                )
                + " | "
                + str(radar_targets[i]["Distance (NM)"])
                + " NM"
            ),
            key="radar_aircraft_picker"
        )

        selected_plane = radar_targets[picker_index]

        st.session_state.selected_icao = selected_plane["ICAO"]

        show_aircraft_details(selected_plane)

        st.markdown("### ALL DETECTED AIRCRAFT")

        st.dataframe(
            pd.DataFrame(radar_targets),
            use_container_width=True,
            hide_index=True
        )

    else:
        st.warning(
            "No aircraft found inside the selected radar radius."
        )

    with st.expander("RADAR DIAGNOSTICS"):
        st.write("API aircraft:", st.session_state.api_total)
        st.write("Valid aircraft:", len(aircraft))
        st.write("Radar targets:", len(radar_targets))

# ==========================================
# AIRCRAFT MAP (ট্রেইল সহ উন্নত ম্যাপ)
# ==========================================

elif page == "Aircraft Map":

    st.subheader("🌍 AIRCRAFT POSITION MAP")

    st.info(
        "This map shows aircraft in the selected scan area, "
        "along with their past trajectory lines."
    )

    if radar_targets:

        map_df = pd.DataFrame(radar_targets)

        fig = px.scatter_map(
            map_df,
            lat="Latitude",
            lon="Longitude",
            hover_name="Callsign",
            hover_data=[
                "ICAO",
                "Aircraft Type",
                "Altitude (ft)",
                "Ground Speed (knots)",
                "Distance (NM)"
            ],
            zoom=5,
            height=650
        )

        fig.update_traces(
            marker=dict(
                size=10,
                color="#39ff91"
            )
        )

        fig.update_layout(
            map_style="open-street-map",
            paper_bgcolor="#050b10",
            font_color="#d9ffe9",
            margin=dict(l=0, r=0, t=0, b=0)
        )

        st.plotly_chart(
            fig,
            use_container_width=True
        )

    else:
        st.warning("No aircraft available.")

# ==========================================
# FLIGHT SEARCH
# ==========================================

elif page == "Flight Search":

    st.subheader("🔎 FLIGHT IDENTIFICATION")

    with st.form("search_form"):

        query = st.text_input(
            "Flight Callsign / ICAO Hex",
            placeholder="Example: BAW123"
        )

        submitted = st.form_submit_button(
            "SEARCH AIRCRAFT",
            use_container_width=True
        )

    if submitted:

        with st.spinner("Searching aircraft..."):

            results, error = search_flight(query)

        st.session_state.search_results = results

        if error:
            st.error(error)

        elif results:
            st.success(f"Found {len(results)} aircraft.")

        else:
            st.warning("No matching aircraft found.")

    results = st.session_state.search_results

    if results:

        selected = st.selectbox(
            "Select aircraft",
            range(len(results)),
            format_func=lambda i: (
                results[i]["Callsign"]
                or results[i]["ICAO"]
            )
        )

        plane = results[selected].copy()

        distance, bearing = distance_bearing(
            center_lat,
            center_lon,
            plane["Latitude"],
            plane["Longitude"]
        )

        plane["Distance (NM)"] = round(distance, 1)
        plane["Direction (°)"] = round(bearing, 1)

        show_aircraft_details(plane)

# ==========================================
# AIRCRAFT DATABASE
# ==========================================

elif page == "Aircraft Database":

    st.subheader("📡 AIRCRAFT DATABASE")

    search = st.text_input(
        "Filter database",
        placeholder="Callsign, ICAO, aircraft type..."
    )

    database = pd.DataFrame(targets)

    if not database.empty and search.strip():

        term = search.strip().lower()

        mask = database.astype(str).apply(
            lambda column: column.str.lower().str.contains(
                term,
                regex=False
            )
        ).any(axis=1)

        database = database[mask]

    if not database.empty:

        st.dataframe(
            database,
            use_container_width=True,
            hide_index=True
        )

    else:
        st.info("No aircraft records available.")

# ==========================================
# WATCHLIST (নতুন ফিচার পেজ)
# ==========================================

elif page == "Watchlist":
    st.subheader("⭐ FAVORITE AIRCRAFT WATCHLIST")
    
    watchlist_icaos = st.session_state.watchlist
    if not watchlist_icaos:
        st.info("No aircraft added to your watchlist yet. Select a plane from the Radar Scanner and click 'Add Watchlist'.")
    else:
        # বর্তমান টার্গেটের মধ্য থেকে ওয়াচলিস্টের প্লেনগুলো ফিল্টার করা
        watched_planes = [p for p in targets if p["ICAO"] in watchlist_icaos]
        
        if watched_planes:
            st.dataframe(pd.DataFrame(watched_planes), use_container_width=True, hide_index=True)
            
            selected_watchlist_icao = st.selectbox(
                "Inspect Watchlist Aircraft",
                [p["ICAO"] for p in watched_planes]
            )
            for p in watched_planes:
                if p["ICAO"] == selected_watchlist_icao:
                    show_aircraft_details(p)
        else:
            st.warning("None of your watched aircraft are currently inside the active radar radius, but their ICAO are: " + ", ".join(watchlist_icaos))

# ==========================================
# SYSTEM INFORMATION
# ==========================================

elif page == "System Information":

    st.subheader("SYSTEM INFORMATION")

    st.markdown("""
    ### PLAN RADAR X

    Aircraft tracking and visualization interface.

    **Data Provider:** adsb.lol

    **Data Type:** ADS-B / MLAT

    **Features:**
    - Smooth 360-degree radar sweep
    - Aircraft selection & Watchlist (Favorite tracking)
    - Flight trail history and altitude/speed charts
    - Flight information viewer & Interactive Map
    - Callsign and ICAO search
    - Aircraft database & Distance/direction calculation

    **Important limitations:**
    - This is not a primary radar.
    - The rotating sweep is a visual effect.
    - Aircraft data depends on receiver coverage.
    - Selected radius is limited to 250 NM.
    - API availability and request limits may change.
    - Aircraft positions may be delayed or unavailable.

    **Data attribution:** ADSB.lol — Open aircraft data.
    **Data licence:** ODbL 1.0.
    """)

    st.markdown(
        "[ADSB.lol API Documentation](https://api.adsb.lol/docs)"
    )

    st.markdown(
        "[ADSB.lol Project](https://www.adsb.lol/)"
    )

# ==========================================
# FOOTER
# ==========================================

st.divider()

st.caption(
    "PLAN RADAR X | 360° Radar Visualization | "
    "Powered by adsb.lol | Aircraft positions are not guaranteed."
)
