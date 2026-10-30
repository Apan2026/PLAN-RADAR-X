import streamlit as st
import requests
import pandas as pd
import plotly.express as px
from datetime import datetime, timezone

try:
    from streamlit_autorefresh import st_autorefresh
    REFRESH_AVAILABLE = True
except ImportError:
    REFRESH_AVAILABLE = False


# =====================================
# CONFIG
# =====================================

st.set_page_config(
    page_title="PLAN RADAR X",
    page_icon="✈️",
    layout="wide"
)

API_URL = "https://opensky-network.org/api/states/all"


# =====================================
# DESIGN
# =====================================

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@500;700;800&family=Inter:wght@400;500;600;700&display=swap');

.stApp {
    background: #07111f;
    color: #eaf2ff;
    font-family: Inter, sans-serif;
}

.block-container {
    max-width: 1550px;
    padding-top: 1.5rem;
}

.hero {
    background: linear-gradient(120deg,#102b45,#101a32);
    border: 1px solid #244665;
    border-radius: 18px;
    padding: 25px;
    margin-bottom: 20px;
}

.hero h1 {
    font-family: Orbitron,sans-serif;
    color: #4de2ff;
    letter-spacing: 3px;
}

.hero p {
    color: #9db7d2;
}

.metric {
    background: #101f32;
    border: 1px solid #213c59;
    border-radius: 13px;
    padding: 17px;
}

.metric-label {
    color: #8da9c5;
    font-size: 13px;
}

.metric-value {
    color: #4de2ff;
    font-family: Orbitron,sans-serif;
    font-size: 24px;
    margin-top: 8px;
}

.section-title {
    font-family: Orbitron,sans-serif;
    color: #4de2ff;
    font-size: 18px;
    margin: 22px 0 12px 0;
}

[data-testid="stSidebar"] {
    background: #0b192a;
}

div.stButton > button {
    background: #087ea4;
    color: white;
    border: 1px solid #27c8ed;
    border-radius: 9px;
    font-weight: 600;
}

</style>
""", unsafe_allow_html=True)


# =====================================
# AIRCRAFT DATA
# =====================================

@st.cache_data(ttl=30, show_spinner=False)
def get_aircraft_data():

    try:
        response = requests.get(
            API_URL,
            headers={"User-Agent": "PLAN-RADAR-X/1.0"},
            timeout=40
        )

        response.raise_for_status()

        data = response.json()
        states = data.get("states")

        if states is None:
            return pd.DataFrame(), "No aircraft data available."

        records = []

        for p in states:

            if len(p) < 17:
                continue

            lat = p[6]
            lon = p[5]

            if lat is None or lon is None:
                continue

            altitude = p[7]
            velocity = p[9]
            heading = p[10]
            vertical_rate = p[11]
            geo_altitude = p[13]

            callsign = str(p[1] or "UNKNOWN").strip().upper()

            records.append({

                "ICAO24": str(p[0]).upper(),
                "Callsign": callsign,
                "Country": p[2] or "Unknown",

                "Longitude": lon,
                "Latitude": lat,

                "Altitude (m)": altitude,

                "Altitude (ft)": (
                    round(altitude * 3.28084)
                    if altitude is not None else None
                ),

                "Geometric Altitude (m)": geo_altitude,

                "Speed (km/h)": (
                    round(velocity * 3.6)
                    if velocity is not None else None
                ),

                "Speed (knots)": (
                    round(velocity * 1.94384)
                    if velocity is not None else None
                ),

                "Heading": heading,
                "Vertical Rate (m/s)": vertical_rate,

                "Squawk": p[14] or "N/A",

                "On Ground": bool(p[8]),

                "Last Contact": p[4],

                "Position Time": p[3],

                "Position Source": p[16]
            })

        return pd.DataFrame(records), None

    except Exception as e:
        return pd.DataFrame(), str(e)


# =====================================
# HEADER
# =====================================

st.markdown("""
<div class="hero">
    <h1>✈ PLAN RADAR X</h1>
    <p>WORLDWIDE AIRCRAFT TRACKING SYSTEM</p>
    <p>Flight Search • Live Map • Aircraft Details</p>
</div>
""", unsafe_allow_html=True)


# =====================================
# SIDEBAR
# =====================================

st.sidebar.title("✈ PLAN RADAR X")

page = st.sidebar.radio(
    "NAVIGATION",
    [
        "Flight Search",
        "Worldwide Map",
        "Aircraft Database",
        "About"
    ]
)

st.sidebar.markdown("---")

refresh = st.sidebar.selectbox(
    "Refresh Interval",
    [30, 60, 120, 300],
    index=1
)

auto_refresh = st.sidebar.checkbox(
    "Auto Refresh",
    value=True
)

if st.sidebar.button("Refresh Now"):
    get_aircraft_data.clear()
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.caption("DATA: OPENSKY NETWORK")
st.sidebar.caption("Created by Apan2026")


if auto_refresh and REFRESH_AVAILABLE:
    st_autorefresh(
        interval=refresh * 1000,
        key="refresh"
    )


# =====================================
# LOAD DATA
# =====================================

with st.spinner("Loading worldwide aircraft data..."):
    df, error = get_aircraft_data()

if error:
    st.error(f"Aircraft data unavailable: {error}")
    st.stop()

if df.empty:
    st.warning("No aircraft with available position data.")
    st.stop()


# =====================================
# SEARCH HELPERS
# =====================================

def normalize(value):
    return "".join(
        char for char in str(value).upper()
        if char.isalnum()
    )


def search_aircraft(query):

    q = normalize(query)

    if not q:
        return pd.DataFrame()

    possible = [q]

    # Biman IATA example BG355 -> ICAO callsign BBC355
    if q.startswith("BG") and len(q) > 2:
        possible.append("BBC" + q[2:])

    callsigns = df["Callsign"].apply(normalize)
    icao_codes = df["ICAO24"].apply(normalize)

    mask = (
        callsigns.isin(possible)
        | icao_codes.eq(q)
    )

    # If exact match is unavailable, allow partial callsign match
    if not mask.any():
        mask = (
            callsigns.str.contains(q, regex=False)
            | icao_codes.str.contains(q, regex=False)
        )

        if q.startswith("BG") and len(q) > 2:
            alternative = "BBC" + q[2:]
            mask = (
                mask
                | callsigns.str.contains(
                    alternative,
                    regex=False
                )
            )

    return df[mask].copy()


# =====================================
# MAP FUNCTION
# =====================================

def show_map(data, title="Aircraft Location"):

    if data.empty:
        st.warning("No aircraft location available.")
        return

    map_data = data.copy()

    map_data["Status"] = map_data["On Ground"].map({
        True: "On Ground",
        False: "Airborne"
    })

    map_data["Altitude"] = map_data["Altitude (ft)"].apply(
        lambda x: f"{x:,} ft" if pd.notna(x) else "Unknown"
    )

    map_data["Speed"] = map_data["Speed (knots)"].apply(
        lambda x: f"{x} knots" if pd.notna(x) else "Unknown"
    )

    first = map_data.iloc[0]

    fig = px.scatter_map(
        map_data,
        lat="Latitude",
        lon="Longitude",
        color="Status",
        hover_name="Callsign",
        hover_data=[
            "ICAO24",
            "Country",
            "Altitude",
            "Speed",
            "Heading",
            "Status"
        ],
        color_discrete_map={
            "Airborne": "#00d9ff",
            "On Ground": "#ffb84d"
        },
        zoom=5 if len(map_data) == 1 else 1,
        height=620
    )

    fig.update_layout(
        title=title,
        map=dict(
            style="open-street-map",
            center={
                "lat": float(first["Latitude"]),
                "lon": float(first["Longitude"])
            },
            zoom=5 if len(map_data) == 1 else 1
        ),
        paper_bgcolor="#07111f",
        plot_bgcolor="#07111f",
        font_color="white",
        margin=dict(l=0, r=0, t=50, b=0)
    )

    fig.update_traces(
        marker=dict(size=12, opacity=0.9)
    )

    st.plotly_chart(
        fig,
        use_container_width=True,
        config={
            "scrollZoom": True,
            "displaylogo": False
        }
    )


# =====================================
# FLIGHT DETAILS
# =====================================

def show_details(plane):

    st.markdown(
        '<div class="section-title">✈ FLIGHT INFORMATION</div>',
        unsafe_allow_html=True
    )

    st.subheader(
        f'Flight: {plane["Callsign"]}'
    )

    a, b, c = st.columns(3)

    a.metric("Callsign", plane["Callsign"])
    b.metric("ICAO24", plane["ICAO24"])
    c.metric("Country", plane["Country"])

    a, b, c = st.columns(3)

    altitude = plane["Altitude (ft)"]
    speed = plane["Speed (knots)"]
    heading = plane["Heading"]

    a.metric(
        "Altitude",
        f"{altitude:,} ft" if pd.notna(altitude) else "Unknown"
    )

    b.metric(
        "Speed",
        f"{speed} knots" if pd.notna(speed) else "Unknown"
    )

    c.metric(
        "Heading",
        f"{heading}°" if pd.notna(heading) else "Unknown"
    )

    a, b, c = st.columns(3)

    a.metric(
        "Flight Status",
        "On Ground" if plane["On Ground"] else "Airborne"
    )

    b.metric(
        "Squawk",
        plane["Squawk"]
    )

    vr = plane["Vertical Rate (m/s)"]

    c.metric(
        "Vertical Rate",
        f"{vr} m/s" if pd.notna(vr) else "Unknown"
    )

    st.markdown("### 📍 Aircraft Location")

    st.code(
        f'Latitude: {plane["Latitude"]}\n'
        f'Longitude: {plane["Longitude"]}'
    )

    st.markdown("### 📡 Additional Information")

    details = {
        "Geometric Altitude (m)": plane["Geometric Altitude (m)"],
        "Barometric Altitude (m)": plane["Altitude (m)"],
        "Position Source": plane["Position Source"],
        "Last Contact (Unix)": plane["Last Contact"],
        "Position Time (Unix)": plane["Position Time"]
    }

    st.dataframe(
        pd.DataFrame(
            list(details.items()),
            columns=["Information", "Value"]
        ),
        use_container_width=True,
        hide_index=True
    )

    st.caption(
        "Only fields supplied by the data provider can be displayed. "
        "Departure, destination and aircraft model are not included "
        "in this OpenSky response."
    )


# =====================================
# PAGE 1: FLIGHT SEARCH
# =====================================

if page == "Flight Search":

    st.markdown(
        '<div class="section-title">🔎 SEARCH YOUR FLIGHT</div>',
        unsafe_allow_html=True
    )

    with st.form("flight_search_form"):

        query = st.text_input(
            "Enter Flight Number / Callsign / ICAO24",
            placeholder="Example: BBC355 or BG355"
        )

        submitted = st.form_submit_button(
            "🔍 SEARCH FLIGHT",
            use_container_width=True
        )

    if submitted:

        if query.strip():

            st.session_state["flight_query"] = query.strip()

        else:

            st.session_state["flight_query"] = ""

    if "flight_query" in st.session_state:

        current_query = st.session_state["flight_query"]

        if current_query:

            results = search_aircraft(current_query)

            if not results.empty:

                st.success(
                    f"Found {len(results)} matching aircraft."
                )

                for index, (_, plane) in enumerate(
                    results.iterrows()
                ):

                    st.markdown("---")

                    st.markdown(
                        f'### ✈ {plane["Callsign"]}'
                    )

                    # Map opens immediately after search
                    show_map(
                        pd.DataFrame([plane]),
                        f'Flight Location - {plane["Callsign"]}'
                    )

                    show_details(plane)

            else:

                st.error(
                    "No matching aircraft found in the available data."
                )

                st.info(
                    "The aircraft may not be transmitting visible ADS-B "
                    "position data right now. Try again later or search "
                    "using its ICAO callsigns."
                )

                st.caption(
                    "For Biman Bangladesh, try BBC355 or BG355. "
                    "These are search examples, not guaranteed live flights."
                )


# =====================================
# PAGE 2: WORLDWIDE MAP
# =====================================

elif page == "Worldwide Map":

    st.markdown(
        '<div class="section-title">🌍 WORLDWIDE AIRCRAFT MAP</div>',
        unsafe_allow_html=True
    )

    show_map(
        df,
        "PLAN RADAR X - Worldwide Aircraft"
    )

    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True
    )


# =====================================
# PAGE 3: DATABASE
# =====================================

elif page == "Aircraft Database":

    st.markdown(
        '<div class="section-title">📡 AIRCRAFT DATABASE</div>',
        unsafe_allow_html=True
    )

    countries = [
        "All Countries"
    ] + sorted(
        df["Country"].dropna().unique().tolist()
    )

    selected = st.selectbox(
        "Select Country",
        countries
    )

    filtered = df.copy()

    if selected != "All Countries":
        filtered = filtered[
            filtered["Country"] == selected
        ]

    status = st.selectbox(
        "Aircraft Status",
        ["All", "Airborne", "On Ground"]
    )

    if status == "Airborne":
        filtered = filtered[~filtered["On Ground"]]

    elif status == "On Ground":
        filtered = filtered[filtered["On Ground"]]

    st.write(f"Aircraft found: {len(filtered)}")

    show_map(filtered, "Aircraft Database Map")

    st.dataframe(
        filtered,
        use_container_width=True,
        hide_index=True
    )

    st.download_button(
        "Download CSV",
        filtered.to_csv(index=False).encode("utf-8"),
        "aircraft_database.csv",
        "text/csv"
    )


# =====================================
# PAGE 4: ABOUT
# =====================================

elif page == "About":

    st.title("About PLAN RADAR X")

    st.write("""
    PLAN RADAR X is a worldwide aircraft tracking application.

    DATA SOURCE:
    OpenSky Network ADS-B API.

    FEATURES:
    - Flight search
    - Individual aircraft map
    - Aircraft details
    - Worldwide aircraft map
    - Aircraft database
    - Country filter
    - CSV export

    LIMITATIONS:
    This is not a physical primary radar.
    Aircraft visibility depends on ADS-B coverage and API data.
    Departure airport, destination airport, aircraft model and
    full flight history are not supplied by this API response.
    """)

    st.markdown(
        "[OpenSky Network](https://opensky-network.org/)"
    )


# =====================================
# FOOTER
# =====================================

st.markdown("---")

st.caption(
    "PLAN RADAR X | Created by Apan2026 | "
    + datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
)
