
import streamlit as st
import requests
import pandas as pd
import plotly.express as px
import streamlit.components.v1 as components
import math
import html
from datetime import datetime, timezone

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
    padding: 15px;
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
    "total_api": 0,
    "last_update": None,
    "api_error": None,
    "search_results": [],
    "auto_refresh": False
}

for key, value in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value

# ==========================================
# API
# ==========================================

def api_request(endpoint):
    try:
        response = requests.get(
            API + endpoint,
            headers={"User-Agent": "PLAN-RADAR-X/2.0"},
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
        return None, f"API HTTP error: {e}"

    except (requests.exceptions.RequestException, ValueError) as e:
        return None, str(e)


# ==========================================
# AIRCRAFT NORMALIZATION
# ==========================================

def normalize_aircraft(items):
    result = []

    for plane in items or []:
        try:
            lat = float(plane["lat"])
            lon = float(plane["lon"])

            if not (-90 <= lat <= 90):
                continue

            if not (-180 <= lon <= 180):
                continue

        except (KeyError, TypeError, ValueError):
            continue

        altitude = plane.get("alt_baro")

        result.append({
            "ICAO": plane.get("hex", ""),
            "Callsign": str(plane.get("flight") or "").strip(),
            "Registration": plane.get("r", ""),
            "Aircraft Type": plane.get("t", ""),
            "Latitude": lat,
            "Longitude": lon,
            "Altitude (ft)": altitude,
            "Ground Speed (knots)": plane.get("gs"),
            "Heading": plane.get("track"),
            "Vertical Rate": plane.get("baro_rate"),
            "Squawk": plane.get("squawk", ""),
            "On Ground": altitude == "ground",
            "Category": plane.get("category", ""),
            "Messages": plane.get("messages"),
            "Seen (seconds)": plane.get("seen"),
            "Distance (NM)": plane.get("dst"),
            "Direction": plane.get("dir"),
            "Source": plane.get("type", "")
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

    raw_aircraft = data.get("ac") or []
    total = data.get("total", len(raw_aircraft))

    aircraft = normalize_aircraft(raw_aircraft)

    return aircraft, total, None


# ==========================================
# FLIGHT SEARCH
# ==========================================

def search_flight(query):
    query = query.strip().upper()

    if not query:
        return [], "Enter a callsign or ICAO hex."

    endpoint = "/callsign/" + requests.utils.quote(query, safe="")
    data, error = api_request(endpoint)

    if error:
        return [], error

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
    dlon = math.radians(lon2 - lon1)

    y = math.sin(dlon) * math.cos(rlat2)

    x = (
        math.cos(rlat1) * math.sin(rlat2)
        - math.sin(rlat1) * math.cos(rlat2)
        * math.cos(dlon)
    )

    bearing = (math.degrees(math.atan2(y, x)) + 360) % 360

    a = (
        math.sin((rlat2 - rlat1) / 2) ** 2
        + math.cos(rlat1) * math.cos(rlat2)
        * math.sin(dlon / 2) ** 2
    )

    distance_km = 6371 * 2 * math.atan2(
        math.sqrt(a),
        math.sqrt(max(0, 1 - a))
    )

    return distance_km / 1.852, bearing


# ==========================================
# RADAR
# ==========================================

def create_radar(aircraft, center_lat, center_lon, radius):

    dots = []
    visible_count = 0

    for plane in aircraft:
        distance, bearing = distance_bearing(
            center_lat,
            center_lon,
            plane["Latitude"],
            plane["Longitude"]
        )

        if distance > radius:
            continue

        visible_count += 1

        angle = math.radians(bearing - 90)
        scale = (distance / radius) * 43

        x = 50 + math.cos(angle) * scale
        y = 50 + math.sin(angle) * scale

        callsign = html.escape(
            plane["Callsign"] or plane["ICAO"]
        )

        altitude = html.escape(
            str(plane["Altitude (ft)"] or "Unknown")
        )

        tooltip = html.escape(
            f"{callsign} | {distance:.1f} NM | {altitude} ft"
        )

        dots.append(
            f'<div class="target" '
            f'style="left:{x:.2f}%;top:{y:.2f}%;" '
            f'title="{tooltip}"></div>'
        )

    targets = "\n".join(dots)

    radar_html = """
    <!DOCTYPE html>
    <html>
    <head>
    <style>
    * { box-sizing: border-box; }

    body {
        margin: 0;
        background: #050b10;
        font-family: Arial, sans-serif;
        color: #52ff9b;
    }

    .container {
        width: 100%;
        display: flex;
        justify-content: center;
        align-items: center;
        padding: 10px;
    }

    .radar {
        position: relative;
        width: min(88vw, 570px);
        aspect-ratio: 1 / 1;
        border-radius: 50%;
        overflow: hidden;
        border: 2px solid #39ff91;
        background:
            radial-gradient(circle,
                transparent 19.5%,
                #174a35 20%,
                transparent 20.5%,
                transparent 39.5%,
                #174a35 40%,
                transparent 40.5%,
                transparent 59.5%,
                #174a35 60%,
                transparent 60.5%,
                transparent 79.5%,
                #174a35 80%,
                transparent 80.5%),
            radial-gradient(circle, #0b251b, #06100e);
        box-shadow:
            0 0 20px #18ff83,
            inset 0 0 35px #0d5536;
    }

    .cross {
        position: absolute;
        background: #174a35;
    }

    .horizontal {
        width: 100%;
        height: 1px;
        top: 50%;
    }

    .vertical {
        height: 100%;
        width: 1px;
        left: 50%;
    }

    .sweep {
        position: absolute;
        inset: 0;
        border-radius: 50%;
        background: conic-gradient(
            from 0deg,
            transparent 0deg,
            transparent 285deg,
            rgba(20,255,120,0.02) 310deg,
            rgba(20,255,120,0.16) 340deg,
            rgba(20,255,120,0.75) 359deg,
            transparent 360deg
        );
        animation: rotateRadar 3s linear infinite;
    }

    @keyframes rotateRadar {
        from { transform: rotate(0deg); }
        to { transform: rotate(360deg); }
    }

    .target {
        position: absolute;
        width: 9px;
        height: 9px;
        background: #ffffff;
        border-radius: 50%;
        transform: translate(-50%, -50%);
        box-shadow:
            0 0 6px white,
            0 0 13px #39ff91,
            0 0 22px #39ff91;
        z-index: 5;
    }

    .center {
        position: absolute;
        left: 50%;
        top: 50%;
        width: 11px;
        height: 11px;
        border-radius: 50%;
        background: white;
        transform: translate(-50%, -50%);
        box-shadow: 0 0 15px #39ff91;
        z-index: 6;
    }

    .label {
        position: absolute;
        font-size: 11px;
        color: #6effa5;
        z-index: 7;
    }

    .north {
        top: 8px;
        left: 50%;
        transform: translateX(-50%);
    }

    .east {
        right: 8px;
        top: 50%;
    }

    .south {
        bottom: 8px;
        left: 50%;
        transform: translateX(-50%);
    }

    .west {
        left: 8px;
        top: 50%;
    }

    .status {
        text-align: center;
        color: #52ff9b;
        font-size: 12px;
        letter-spacing: 3px;
        margin-top: 12px;
    }
    </style>
    </head>
    <body>
    <div class="container">
      <div class="radar">
        <div class="cross horizontal"></div>
        <div class="cross vertical"></div>
        <div class="sweep"></div>
        <div class="center"></div>

        <div class="label north">N</div>
        <div class="label east">E</div>
        <div class="label south">S</div>
        <div class="label west">W</div>

        TARGETS_PLACEHOLDER
      </div>
    </div>
    <div class="status">● RADAR SCANNING · ADS-B NETWORK</div>
    </body>
    </html>
    """

    return radar_html.replace("TARGETS_PLACEHOLDER", targets), visible_count


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
        "Worldwide Map",
        "Flight Search",
        "Aircraft Database",
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

auto_refresh = st.sidebar.checkbox(
    "Auto refresh (30 seconds)",
    value=st.session_state.auto_refresh
)

st.session_state.auto_refresh = auto_refresh

# ==========================================
# FETCH DATA
# ==========================================

should_scan = refresh or st.session_state.last_update is None

if should_scan:
    with st.spinner("Scanning aircraft network..."):
        aircraft_data, total, error = fetch_area(
            center_lat,
            center_lon,
            radius
        )

    if aircraft_data is not None:
        st.session_state.aircraft = aircraft_data
        st.session_state.total_api = total
        st.session_state.last_update = datetime.now(timezone.utc)
        st.session_state.api_error = None
    else:
        st.session_state.api_error = error

aircraft = st.session_state.aircraft

# ==========================================
# AUTO REFRESH
# ==========================================

if auto_refresh:
    st.info(
        "Auto refresh is enabled. "
        "Use the browser refresh or scan button for a new scan."
    )

# ==========================================
# STATUS
# ==========================================

if st.session_state.api_error:
    st.error(st.session_state.api_error)

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
# METRICS
# ==========================================

col1, col2, col3, col4 = st.columns(4)

col1.metric("VALID AIRCRAFT", len(aircraft))
col2.metric("API AIRCRAFT", st.session_state.total_api)

col3.metric(
    "AIRBORNE",
    sum(1 for p in aircraft if not p["On Ground"])
)

col4.metric("SCAN RADIUS", f"{radius} NM")

st.divider()

# ==========================================
# RADAR SCANNER
# ==========================================

if page == "Radar Scanner":

    st.subheader("◉ Circular Radar Scanner")

    st.caption(
        "Aircraft positions received from the ADS-B network."
    )

    radar, visible_count = create_radar(
        aircraft,
        center_lat,
        center_lon,
        radius
    )

    components.html(
        radar,
        height=620,
        scrolling=False
    )

    st.metric("TARGETS INSIDE RADAR", visible_count)

    st.markdown("### DETECTED TARGETS")

    if aircraft:
        target_df = pd.DataFrame(aircraft)

        st.dataframe(
            target_df[
                [
                    "Callsign",
                    "ICAO",
                    "Registration",
                    "Aircraft Type",
                    "Altitude (ft)",
                    "Ground Speed (knots)",
                    "Heading",
                    "Distance (NM)",
                    "Latitude",
                    "Longitude"
                ]
            ],
            use_container_width=True,
            hide_index=True
        )
    else:
        st.warning(
            "No valid aircraft positions received. "
            "Check API status or try another scan area."
        )

# ==========================================
# WORLDWIDE MAP
# ==========================================

elif page == "Worldwide Map":

    st.subheader("🌍 Aircraft Position Map")

    st.info(
        "This map displays aircraft inside your selected "
        "center and radius. It is not a complete worldwide feed."
    )

    if aircraft:
        map_df = pd.DataFrame(aircraft)

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
                "Heading"
            ],
            zoom=4,
            height=650
        )

        fig.update_traces(
            marker=dict(size=9, color="#39ff91")
        )

        fig.update_layout(
            map_style="open-street-map",
            paper_bgcolor="#050b10",
            font_color="#d9ffe9",
            margin=dict(l=0, r=0, t=0, b=0)
        )

        st.plotly_chart(fig, use_container_width=True)

    else:
        st.warning("No aircraft available for the map.")

# ==========================================
# FLIGHT SEARCH
# ==========================================

elif page == "Flight Search":

    st.subheader("🔎 Flight Identification")

    with st.form("search_form"):
        query = st.text_input(
            "Flight Callsign / ICAO Hex",
            placeholder="Example: AXB2893"
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
        search_df = pd.DataFrame(results)

        st.dataframe(
            search_df,
            use_container_width=True,
            hide_index=True
        )

        selected = st.selectbox(
            "Select aircraft",
            range(len(results)),
            format_func=lambda i: (
                results[i]["Callsign"] or results[i]["ICAO"]
            )
        )

        st.markdown("### SELECTED AIRCRAFT DETAILS")

        for key, value in results[selected].items():
            st.write(f"**{key}:** {value}")

# ==========================================
# AIRCRAFT DATABASE
# ==========================================

elif page == "Aircraft Database":

    st.subheader("📡 Aircraft Database")

    search = st.text_input(
        "Filter database",
        placeholder="Callsign, ICAO, aircraft type..."
    )

    database = pd.DataFrame(aircraft)

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
# SYSTEM INFORMATION
# ==========================================

elif page == "System Information":

    st.subheader("SYSTEM INFORMATION")

    st.markdown("""
    ### PLAN RADAR X

    **Data Provider:** adsb.lol

    **Data Type:** ADS-B / MLAT

    **Features:**
    - Circular animated radar
    - Rotating radar sweep
    - Aircraft position markers
    - Detection radius up to 250 NM
    - Aircraft database
    - Callsign search
    - Aircraft detail viewer
    - Interactive map

    **Important limitations:**
    - This is not a real primary radar.
    - The animated sweep is a visual effect.
    - Aircraft data depends on receiver coverage.
    - API availability and limits may change.
    - This version does not guarantee worldwide coverage.

    **Data attribution:**
    ADSB.lol — Open aircraft data.
    Data licence: ODbL 1.0.
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
    "PLAN RADAR X | Powered by adsb.lol | "
    "Aircraft positions are not guaranteed."
)
