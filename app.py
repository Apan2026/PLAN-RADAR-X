
import streamlit as st
import requests
import pandas as pd
import plotly.express as px
import streamlit.components.v1 as components
import math
import json
import html
from datetime import datetime, timezone

# ==========================================
# CONFIGURATION
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
DEFAULT_RADIUS = 100

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
.panel {
    background: #0a1a19;
    border: 1px solid #205a42;
    padding: 15px;
    border-radius: 10px;
}
</style>
""", unsafe_allow_html=True)


# ==========================================
# SESSION STATE
# ==========================================

if "aircraft" not in st.session_state:
    st.session_state.aircraft = []

if "last_update" not in st.session_state:
    st.session_state.last_update = None

if "api_error" not in st.session_state:
    st.session_state.api_error = None

if "search_results" not in st.session_state:
    st.session_state.search_results = []


# ==========================================
# API REQUEST
# ==========================================

def api_request(endpoint):
    url = API + endpoint

    try:
        response = requests.get(
            url,
            headers={"User-Agent": "PLAN-RADAR-X/1.0"},
            timeout=(8, 20)
        )

        if response.status_code == 429:
            return None, "API rate limit reached. Wait before retrying."

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
# NORMALIZE AIRCRAFT DATA
# ==========================================

def normalize_aircraft(items):
    result = []

    for plane in items or []:
        lat = plane.get("lat")
        lon = plane.get("lon")

        if lat is None or lon is None:
            continue

        try:
            lat = float(lat)
            lon = float(lon)

            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                continue

        except (ValueError, TypeError):
            continue

        result.append({
            "ICAO": plane.get("hex", ""),
            "Callsign": str(plane.get("flight") or "").strip(),
            "Registration": plane.get("r"),
            "Aircraft Type": plane.get("t"),
            "Latitude": lat,
            "Longitude": lon,
            "Altitude (ft)": plane.get("alt_baro"),
            "Ground Speed (knots)": plane.get("gs"),
            "Heading": plane.get("track"),
            "Vertical Rate": plane.get("baro_rate"),
            "Squawk": plane.get("squawk"),
            "On Ground": plane.get("alt_baro") == "ground",
            "Category": plane.get("category"),
            "Messages": plane.get("messages"),
            "Seen (seconds)": plane.get("seen"),
            "Source": plane.get("type")
        })

    return result


# ==========================================
# LOAD AIRCRAFT AROUND LOCATION
# ==========================================

def fetch_area(lat, lon, radius):
    endpoint = (
        f"/lat/{lat}/lon/{lon}/dist/{radius}"
    )

    data, error = api_request(endpoint)

    if error:
        return None, error

    if not isinstance(data, dict):
        return None, "Unexpected API response."

    aircraft = normalize_aircraft(data.get("ac", []))

    return aircraft, None


# ==========================================
# SEARCH FLIGHT
# ==========================================

def search_flight(query):
    query = query.strip().upper()

    if not query:
        return [], "Enter a flight number or ICAO address."

    endpoint = "/callsign/" + requests.utils.quote(query, safe="")

    data, error = api_request(endpoint)

    if error:
        return [], error

    if not isinstance(data, dict):
        return [], "Unexpected API response."

    results = normalize_aircraft(data.get("ac", []))

    if not results:
        # Try ICAO hex search.
        if len(query) == 6:
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
        math.sqrt(a), math.sqrt(1 - a)
    )

    distance_nm = distance_km / 1.852

    return distance_nm, bearing


# ==========================================
# RADAR HTML
# ==========================================

def create_radar(aircraft, center_lat, center_lon, radius):

    dots = []

    for plane in aircraft:
        distance, bearing = distance_bearing(
            center_lat,
            center_lon,
            plane["Latitude"],
            plane["Longitude"]
        )

        if distance > radius:
            continue

        angle = math.radians(bearing - 90)

        # Convert distance to radar position.
        scale = (distance / radius) * 44

        x = 50 + math.cos(angle) * scale
        y = 50 + math.sin(angle) * scale

        callsign = html.escape(
            plane["Callsign"] or plane["ICAO"]
        )

        title = html.escape(
            f"{callsign} | {distance:.1f} NM"
        )

        dots.append(
            f'<div class="target" '
            f'style="left:{x:.2f}%;top:{y:.2f}%;" '
            f'title="{title}"></div>'
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
            0 0 15px #18ff83,
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
            transparent 290deg,
            rgba(20,255,120,0.02) 315deg,
            rgba(20,255,120,0.12) 340deg,
            rgba(20,255,120,0.65) 359deg,
            transparent 360deg
        );
        animation: rotateRadar 4s linear infinite;
    }

    @keyframes rotateRadar {
        from { transform: rotate(0deg); }
        to { transform: rotate(360deg); }
    }

    .target {
        position: absolute;
        width: 8px;
        height: 8px;
        background: #a3ffb9;
        border-radius: 50%;
        transform: translate(-50%, -50%);
        box-shadow:
            0 0 5px #ffffff,
            0 0 12px #39ff91,
            0 0 20px #39ff91;
        z-index: 5;
    }

    .center {
        position: absolute;
        left: 50%;
        top: 50%;
        width: 10px;
        height: 10px;
        border-radius: 50%;
        background: #ffffff;
        transform: translate(-50%, -50%);
        box-shadow: 0 0 12px #39ff91;
        z-index: 6;
    }

    .label {
        position: absolute;
        font-size: 10px;
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
    <div class="status">● RADAR SCANNING · ADS-B DATA</div>
    </body>
    </html>
    """

    return radar_html.replace("TARGETS_PLACEHOLDER", targets)


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

st.sidebar.caption(
    "Default center: Dhaka, Bangladesh"
)

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

        aircraft, error = fetch_area(
            center_lat,
            center_lon,
            radius
        )

    if aircraft is not None:
        st.session_state.aircraft = aircraft
        st.session_state.last_update = datetime.now(
            timezone.utc
        )
        st.session_state.api_error = None

    else:
        st.session_state.api_error = error


aircraft = st.session_state.aircraft


# ==========================================
# STATUS
# ==========================================

if st.session_state.api_error:
    st.error(st.session_state.api_error)

    if st.session_state.last_update:
        st.warning(
            "Showing previously received data. "
            "It may not be live."
        )

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

col1, col2, col3 = st.columns(3)

col1.metric("DETECTED AIRCRAFT", len(aircraft))

col2.metric(
    "AIRBORNE",
    sum(1 for p in aircraft if not p["On Ground"])
)

col3.metric(
    "SCAN RADIUS",
    f"{radius} NM"
)

st.divider()


# ==========================================
# RADAR SCANNER
# ==========================================

if page == "Radar Scanner":

    st.subheader("◉ Circular Radar Scanner")

    st.caption(
        "Animated sweep with aircraft positions received "
        "from the ADS-B network."
    )

    radar = create_radar(
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

    st.markdown("### DETECTED TARGETS")

    if aircraft:

        target_df = pd.DataFrame(aircraft)

        st.dataframe(
            target_df[
                [
                    "Callsign",
                    "ICAO",
                    "Aircraft Type",
                    "Altitude (ft)",
                    "Ground Speed (knots)",
                    "Heading",
                    "Latitude",
                    "Longitude"
                ]
            ],
            use_container_width=True,
            hide_index=True
        )

    else:
        st.info(
            "No aircraft positions detected in this scan area. "
            "Try increasing the detection radius."
        )


# ==========================================
# WORLDWIDE MAP
# ==========================================

elif page == "Worldwide Map":

    st.subheader("🌍 Aircraft Position Map")

    st.info(
        "This map shows aircraft within your selected "
        "radar center and radius, not every aircraft worldwide."
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
            zoom=5,
            height=650
        )

        fig.update_traces(
            marker=dict(
                size=9,
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
        st.warning("No aircraft available for the map.")


# ==========================================
# FLIGHT SEARCH
# ==========================================

elif page == "Flight Search":

    st.subheader("🔎 Flight Identification")

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
            st.success(
                f"Found {len(results)} aircraft."
            )

        else:
            st.warning(
                "No matching aircraft found in current API data."
            )

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
                results[i]["Callsign"]
                or results[i]["ICAO"]
            )
        )

        st.markdown("### SELECTED AIRCRAFT DETAILS")

        selected_plane = results[selected]

        for key, value in selected_plane.items():
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

    Advanced aircraft tracking and visualization interface.

    **Data Provider:** adsb.lol

    **Data Type:** ADS-B / MLAT

    **Features:**
    - Circular animated radar
    - Rotating scan beam
    - Aircraft position markers
    - Detection radius control
    - Aircraft database
    - Callsign search
    - Aircraft detail viewer
    - Interactive map

    **Important limitations:**
    - This is not a real primary radar.
    - The animated sweep is a visual effect.
    - Aircraft data depends on receiver coverage.
    - The selected radius is limited to 250 NM.
    - API availability and request limits may change.
    - This version does not provide guaranteed worldwide
      coverage or continuous real-time updates.

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
    "PLAN RADAR X | Aircraft visualization system | "
    "Powered by adsb.lol | ADS-B positions are not guaranteed."
)
