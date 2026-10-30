
import streamlit as st
import requests
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import math
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
DEFAULT_RADIUS = 250


# ==========================================
# CSS DESIGN
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

.info-panel {
    background: #0a1a19;
    border: 1px solid #205a42;
    padding: 18px;
    border-radius: 12px;
}

.small-label {
    color: #66bd91;
    font-size: 12px;
    letter-spacing: 1px;
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
    "scan_center": (DEFAULT_LAT, DEFAULT_LON),
    "scan_radius": DEFAULT_RADIUS
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
            headers={
                "User-Agent": "PLAN-RADAR-X/3.0"
            },
            timeout=(10, 25)
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

        result.append({

            "ICAO": str(
                plane.get("hex") or ""
            ).upper(),

            "Callsign": str(
                plane.get("flight") or ""
            ).strip(),

            "Registration": plane.get("r"),

            "Aircraft Type": plane.get("t"),

            "Latitude": lat,

            "Longitude": lon,

            "Altitude (ft)": plane.get("alt_baro"),

            "Ground Speed (knots)": plane.get("gs"),

            "Heading": plane.get("track"),

            "Vertical Rate": plane.get("baro_rate"),

            "Squawk": plane.get("squawk"),

            "On Ground": (
                plane.get("alt_baro") == "ground"
            ),

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

    endpoint = (
        f"/lat/{lat}/lon/{lon}/dist/{radius}"
    )

    data, error = api_request(endpoint)

    if error:
        return None, 0, error

    if not isinstance(data, dict):
        return None, 0, "Unexpected API response."

    raw = data.get("ac") or []

    total = data.get("total", len(raw))

    aircraft = normalize_aircraft(raw)

    return aircraft, total, None


# ==========================================
# SEARCH FLIGHT
# ==========================================

def search_flight(query):

    query = query.strip().upper()

    if not query:
        return [], "Enter a flight number or ICAO."

    endpoint = (
        "/callsign/"
        + requests.utils.quote(query, safe="")
    )

    data, error = api_request(endpoint)

    if error:
        return [], error

    results = []

    if isinstance(data, dict):
        results = normalize_aircraft(
            data.get("ac", [])
        )

    if not results and len(query) == 6:

        data, error = api_request(
            "/hex/" + query
        )

        if error:
            return [], error

        if isinstance(data, dict):
            results = normalize_aircraft(
                data.get("ac", [])
            )

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
        + math.cos(rlat1)
        * math.cos(rlat2)
        * math.sin(dlon / 2) ** 2
    )

    distance_km = (
        6371
        * 2
        * math.atan2(
            math.sqrt(a),
            math.sqrt(max(0, 1 - a))
        )
    )

    y = (
        math.sin(dlon)
        * math.cos(rlat2)
    )

    x = (
        math.cos(rlat1) * math.sin(rlat2)
        - math.sin(rlat1)
        * math.cos(rlat2)
        * math.cos(dlon)
    )

    bearing = (
        math.degrees(math.atan2(y, x)) + 360
    ) % 360

    return distance_km / 1.852, bearing


# ==========================================
# PREPARE AIRCRAFT DATA
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
# RADAR CHART
# ==========================================

def create_radar_chart(targets, radius, selected_icao):

    fig = go.Figure()

    # Radar circles
    for percentage in [0.2, 0.4, 0.6, 0.8, 1.0]:

        fig.add_shape(
            type="circle",
            x0=-percentage,
            y0=-percentage,
            x1=percentage,
            y1=percentage,
            line=dict(
                color="#174a35",
                width=1.5
            )
        )

    # Cross lines
    fig.add_shape(
        type="line",
        x0=-1, y0=0,
        x1=1, y1=0,
        line=dict(color="#174a35", width=1)
    )

    fig.add_shape(
        type="line",
        x0=0, y0=-1,
        x1=0, y1=1,
        line=dict(color="#174a35", width=1)
    )

    # Static radar sweep sector
    fig.add_shape(
        type="path",
        path="M 0,0 L -0.65,-0.76 Q -0.35,-0.25 0,0 Z",
        fillcolor="rgba(0,255,120,0.12)",
        line=dict(width=0)
    )

    # Aircraft points
    x_values = []
    y_values = []
    labels = []
    hover_text = []
    colors = []
    sizes = []

    for plane in targets:

        distance = plane["Distance (NM)"]

        if distance > radius:
            continue

        bearing = plane["Direction (°)"]

        # North is at top
        angle = math.radians(bearing)

        scale = distance / radius

        x = math.sin(angle) * scale
        y = math.cos(angle) * scale

        x_values.append(x)
        y_values.append(y)

        callsign = (
            plane["Callsign"]
            or plane["ICAO"]
            or "UNKNOWN"
        )

        labels.append(callsign)

        hover_text.append(
            f"<b>{callsign}</b><br>"
            f"ICAO: {plane['ICAO']}<br>"
            f"Type: {plane['Aircraft Type']}<br>"
            f"Altitude: {plane['Altitude (ft)']}<br>"
            f"Speed: {plane['Ground Speed (knots)']} knots<br>"
            f"Distance: {distance} NM<br>"
            f"Direction: {bearing}°<br>"
            f"<i>Click to select this aircraft</i>"
        )

        if plane["ICAO"] == selected_icao:
            colors.append("#ffcc45")
            sizes.append(15)
        else:
            colors.append("#ffffff")
            sizes.append(10)

    fig.add_trace(
        go.Scatter(
            x=x_values,
            y=y_values,
            mode="markers",
            marker=dict(
                size=sizes,
                color=colors,
                line=dict(
                    color="#39ff91",
                    width=1.5
                ),
            ),
            text=hover_text,
            customdata=[
                p["ICAO"]
                for p in targets
                if p["Distance (NM)"] <= radius
            ],
            hovertemplate="%{text}<extra></extra>",
            name="Aircraft",
            selected=dict(
                marker=dict(
                    color="#ffcc45",
                    size=16
                )
            ),
            unselected=dict(
                marker=dict(opacity=1)
            )
        )
    )

    # Radar center
    fig.add_trace(
        go.Scatter(
            x=[0],
            y=[0],
            mode="markers",
            marker=dict(
                size=12,
                color="white",
                line=dict(
                    color="#39ff91",
                    width=2
                )
            ),
            hovertemplate="RADAR CENTER<extra></extra>",
            name="Radar Center"
        )
    )

    fig.update_layout(
        height=650,
        paper_bgcolor="#050b10",
        plot_bgcolor="#06130e",
        font=dict(color="#52ff9b"),
        margin=dict(l=20, r=20, t=20, b=20),
        showlegend=False,
        clickmode="event+select",
        dragmode=False,
        xaxis=dict(
            range=[-1.08, 1.08],
            visible=False,
            scaleanchor="y"
        ),
        yaxis=dict(
            range=[-1.08, 1.08],
            visible=False
        )
    )

    return fig


# ==========================================
# AIRCRAFT DETAILS
# ==========================================

def show_aircraft_details(plane):

    st.markdown("---")

    callsign = (
        plane["Callsign"]
        or plane["ICAO"]
        or "UNKNOWN"
    )

    st.markdown(
        f"## ✈ {html.escape(str(callsign))}"
    )

    st.caption(
        "SELECTED AIRCRAFT · FLIGHT INFORMATION"
    )

    a, b, c, d = st.columns(4)

    a.metric(
        "ICAO ADDRESS",
        plane["ICAO"] or "N/A"
    )

    b.metric(
        "AIRCRAFT TYPE",
        plane["Aircraft Type"] or "Unknown"
    )

    c.metric(
        "ALTITUDE",
        str(plane["Altitude (ft)"] or "N/A")
    )

    d.metric(
        "GROUND SPEED",
        (
            f"{plane['Ground Speed (knots)']} kt"
            if plane["Ground Speed (knots)"] is not None
            else "N/A"
        )
    )

    st.markdown("### AIRCRAFT IDENTITY")

    identity = {
        "Callsign": plane["Callsign"],
        "ICAO": plane["ICAO"],
        "Registration": plane["Registration"],
        "Aircraft Type": plane["Aircraft Type"],
        "Category": plane["Category"],
        "Squawk": plane["Squawk"]
    }

    st.dataframe(
        pd.DataFrame(
            list(identity.items()),
            columns=["Field", "Value"]
        ),
        use_container_width=True,
        hide_index=True
    )

    st.markdown("### FLIGHT POSITION")

    position = {
        "Latitude": plane["Latitude"],
        "Longitude": plane["Longitude"],
        "Distance from radar (NM)": plane["Distance (NM)"],
        "Direction (degrees)": plane["Direction (°)"],
        "Heading": plane["Heading"]
    }

    st.dataframe(
        pd.DataFrame(
            list(position.items()),
            columns=["Field", "Value"]
        ),
        use_container_width=True,
        hide_index=True
    )

    st.markdown("### FLIGHT STATUS")

    status = {
        "Altitude (ft)": plane["Altitude (ft)"],
        "Ground Speed (knots)": plane["Ground Speed (knots)"],
        "Vertical Rate": plane["Vertical Rate"],
        "On Ground": plane["On Ground"],
        "Messages": plane["Messages"],
        "Seen (seconds ago)": plane["Seen (seconds)"],
        "Data Source": plane["Source"]
    }

    st.dataframe(
        pd.DataFrame(
            list(status.items()),
            columns=["Field", "Value"]
        ),
        use_container_width=True,
        hide_index=True
    )

    st.info(
        "Aircraft data depends on ADS-B receiver coverage. "
        "Unavailable fields are shown as N/A."
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

        st.session_state.last_update = datetime.now(
            timezone.utc
        )

        st.session_state.api_error = None

        st.session_state.scan_center = (
            center_lat,
            center_lon
        )

        st.session_state.scan_radius = radius

        # Clear old selection after a new scan
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

aircraft = st.session_state.aircraft

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

c1.metric(
    "API AIRCRAFT",
    st.session_state.api_total
)

c2.metric(
    "VALID AIRCRAFT",
    len(aircraft)
)

c3.metric(
    "RADAR TARGETS",
    len(radar_targets)
)

c4.metric(
    "AIRBORNE",
    airborne_count
)

st.divider()


# ==========================================
# RADAR SCANNER
# ==========================================

if page == "Radar Scanner":

    st.subheader("◉ Interactive Circular Radar")

    st.caption(
        "Select an aircraft point to view its complete available information."
    )

    if radar_targets:

        fig = create_radar_chart(
            radar_targets,
            radius,
            st.session_state.selected_icao
        )

        # Interactive Plotly point selection
        event = st.plotly_chart(
            fig,
            use_container_width=True,
            key="interactive_radar",
            on_select="rerun",
            selection_mode="points"
        )

        # Read selected point index
        try:

            selected_points = event.selection.points

            if selected_points:

                point_index = selected_points[-1]["point_index"]

                if 0 <= point_index < len(radar_targets):

                    st.session_state.selected_icao = (
                        radar_targets[point_index]["ICAO"]
                    )

        except (AttributeError, KeyError, IndexError, TypeError):
            pass

        # Find selected aircraft
        selected_plane = None

        for plane in radar_targets:

            if plane["ICAO"] == st.session_state.selected_icao:
                selected_plane = plane
                break

        # Selection fallback and manual picker
        st.markdown("### SELECT AIRCRAFT")

        options = list(range(len(radar_targets)))

        selected_index = None

        for i, plane in enumerate(radar_targets):

            if plane["ICAO"] == st.session_state.selected_icao:
                selected_index = i
                break

        picker_index = st.selectbox(
            "Choose aircraft from detected targets",
            options,
            index=selected_index if selected_index is not None else 0,
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
            key="aircraft_picker"
        )

        picked_plane = radar_targets[picker_index]

        if (
            st.session_state.selected_icao
            != picked_plane["ICAO"]
        ):

            st.session_state.selected_icao = picked_plane["ICAO"]
            selected_plane = picked_plane

        if selected_plane is None:
            selected_plane = picked_plane

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

        st.write(
            "API aircraft:",
            st.session_state.api_total
        )

        st.write(
            "Valid aircraft:",
            len(aircraft)
        )

        st.write(
            "Radar targets:",
            len(radar_targets)
        )


# ==========================================
# AIRCRAFT MAP
# ==========================================

elif page == "Aircraft Map":

    st.subheader("🌍 Aircraft Position Map")

    st.info(
        "Map shows aircraft in the selected scan area, "
        "not every aircraft worldwide."
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
                results[i]["Callsign"]
                or results[i]["ICAO"]
            )
        )

        details = results[selected]

        # Add distance from selected radar center
        distance, bearing = distance_bearing(
            center_lat,
            center_lon,
            details["Latitude"],
            details["Longitude"]
        )

        details = details.copy()
        details["Distance (NM)"] = round(distance, 1)
        details["Direction (°)"] = round(bearing, 1)

        show_aircraft_details(details)


# ==========================================
# AIRCRAFT DATABASE
# ==========================================

elif page == "Aircraft Database":

    st.subheader("📡 Aircraft Database")

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
    - Interactive aircraft radar
    - Aircraft point selection
    - Aircraft information viewer
    - Aircraft position map
    - Callsign and ICAO search
    - Aircraft database
    - Distance and direction calculation

    **Important limitations:**
    - This is not a primary radar.
    - The radar sweep is a visual effect.
    - Aircraft data depends on receiver coverage.
    - Selected radius is limited to 250 NM.
    - API availability and request limits may change.
    - Aircraft positions may be delayed or unavailable.

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
    "PLAN RADAR X | Aircraft tracking interface | "
    "Powered by adsb.lol | Aircraft positions are not guaranteed."
)
