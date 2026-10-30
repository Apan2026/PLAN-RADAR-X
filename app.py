
import streamlit as st
import requests
import pandas as pd
import plotly.express as px
import time
from datetime import datetime, timezone

try:
    from streamlit_autorefresh import st_autorefresh
    AUTO_REFRESH_AVAILABLE = True
except ImportError:
    AUTO_REFRESH_AVAILABLE = False


# ==========================================
# PAGE CONFIGURATION
# ==========================================

st.set_page_config(
    page_title="PLAN RADAR X",
    page_icon="✈️",
    layout="wide",
    initial_sidebar_state="expanded"
)

API_URL = "https://opensky-network.org/api/states/all"

st.markdown("""
<style>
    .stApp {
        background: #07111f;
        color: #eaf2ff;
    }

    [data-testid="stSidebar"] {
        background: #0b1728;
        border-right: 1px solid #1c3552;
    }

    .main-title {
        font-size: 38px;
        font-weight: 900;
        color: #55c7ff;
        letter-spacing: 3px;
    }

    .subtitle {
        color: #91a9c5;
        font-size: 14px;
        letter-spacing: 2px;
    }

    .info-card {
        background: #10243a;
        border: 1px solid #244767;
        padding: 17px;
        border-radius: 12px;
        margin-bottom: 10px;
    }

    .info-label {
        color: #91a9c5;
        font-size: 12px;
    }

    .info-value {
        color: #55c7ff;
        font-size: 23px;
        font-weight: bold;
    }

    div[data-testid="stMetric"] {
        background: #10243a;
        border: 1px solid #244767;
        padding: 15px;
        border-radius: 12px;
    }

    .stButton button {
        background: #087db5;
        color: white;
        border-radius: 8px;
        border: none;
        font-weight: bold;
    }

    .stButton button:hover {
        background: #119bdc;
        color: white;
    }
</style>
""", unsafe_allow_html=True)


# ==========================================
# DATA CONVERSION
# ==========================================

def safe_value(row, index, default=None):
    try:
        value = row[index]
        return default if value is None else value
    except (IndexError, TypeError):
        return default


def utc_time(timestamp):
    if timestamp is None:
        return "Unavailable"

    try:
        return datetime.fromtimestamp(
            timestamp, timezone.utc
        ).strftime("%Y-%m-%d %H:%M:%S UTC")
    except (ValueError, TypeError, OSError):
        return "Unavailable"


def convert_aircraft(states):
    columns = [
        "ICAO24",
        "Callsign",
        "Country",
        "Time Position",
        "Last Contact",
        "Longitude",
        "Latitude",
        "Altitude (m)",
        "On Ground",
        "Speed (m/s)",
        "Heading",
        "Vertical Rate",
        "Sensors",
        "Geometric Altitude (m)",
        "Squawk",
        "SPI",
        "Position Source",
        "Category"
    ]

    records = []

    if not states:
        return pd.DataFrame(columns=columns)

    for row in states:
        if not row:
            continue

        longitude = safe_value(row, 5)
        latitude = safe_value(row, 6)

        # Only show aircraft with a known map position.
        if longitude is None or latitude is None:
            continue

        callsign = safe_value(row, 1, "")
        callsign = str(callsign).strip() if callsign else ""

        records.append({
            "ICAO24": safe_value(row, 0, ""),
            "Callsign": callsign,
            "Country": safe_value(row, 2, "Unknown"),
            "Time Position": safe_value(row, 3),
            "Last Contact": safe_value(row, 4),
            "Longitude": longitude,
            "Latitude": latitude,
            "Altitude (m)": safe_value(row, 7),
            "On Ground": safe_value(row, 8),
            "Speed (m/s)": safe_value(row, 9),
            "Heading": safe_value(row, 10),
            "Vertical Rate": safe_value(row, 11),
            "Sensors": safe_value(row, 12),
            "Geometric Altitude (m)": safe_value(row, 13),
            "Squawk": safe_value(row, 14),
            "SPI": safe_value(row, 15),
            "Position Source": safe_value(row, 16),
            "Category": safe_value(row, 17)
        })

    return pd.DataFrame(records, columns=columns)


# ==========================================
# OPENSKY API WITH RETRIES
# ==========================================

def fetch_opensky():
    """
    Attempts to retrieve worldwide aircraft data.
    Retries after temporary connection errors.
    """

    headers = {
        "User-Agent": "PLAN-RADAR-X/1.0"
    }

    last_error = None

    for attempt in range(1, 4):
        try:
            response = requests.get(
                API_URL,
                headers=headers,
                timeout=(6, 12)
            )

            if response.status_code == 429:
                raise requests.exceptions.HTTPError(
                    "OpenSky API rate limit reached (429)."
                )

            response.raise_for_status()

            result = response.json()
            states = result.get("states") or []

            dataframe = convert_aircraft(states)

            return {
                "data": dataframe,
                "time": datetime.now(timezone.utc),
                "error": None
            }

        except requests.exceptions.Timeout:
            last_error = "OpenSky connection timed out."

        except requests.exceptions.ConnectionError:
            last_error = "Could not connect to OpenSky."

        except requests.exceptions.HTTPError as error:
            last_error = f"OpenSky HTTP error: {error}"

            # Do not repeatedly retry rate-limit or other HTTP errors.
            break

        except (requests.exceptions.RequestException, ValueError) as error:
            last_error = str(error)

        if attempt < 3:
            time.sleep(attempt)

    return {
        "data": None,
        "time": None,
        "error": last_error or "Unknown API error"
    }


# ==========================================
# SESSION STATE
# ==========================================

if "last_flight_data" not in st.session_state:
    st.session_state.last_flight_data = None

if "last_fetch_time" not in st.session_state:
    st.session_state.last_fetch_time = None

if "flight_query" not in st.session_state:
    st.session_state.flight_query = ""

if "api_error" not in st.session_state:
    st.session_state.api_error = None


# ==========================================
# SIDEBAR
# ==========================================

st.sidebar.markdown("## ✈️ PLAN RADAR X")
st.sidebar.caption("WORLDWIDE AIRCRAFT TRACKING")

page = st.sidebar.radio(
    "NAVIGATION",
    [
        "Flight Search",
        "Worldwide Map",
        "Aircraft Database",
        "About"
    ]
)

st.sidebar.divider()

auto_refresh = st.sidebar.checkbox(
    "Enable automatic refresh",
    value=True
)

if auto_refresh and AUTO_REFRESH_AVAILABLE:
    st_autorefresh(
        interval=60000,
        limit=None,
        key="plan_radar_refresh"
    )

st.sidebar.caption("Refresh interval: 60 seconds")

if st.sidebar.button("🔄 Refresh Aircraft Data", use_container_width=True):
    st.session_state.force_refresh = True
else:
    st.session_state.force_refresh = False


# ==========================================
# HEADER
# ==========================================

st.markdown(
    '<div class="main-title">✈ PLAN RADAR X</div>',
    unsafe_allow_html=True
)

st.markdown(
    '<div class="subtitle">GLOBAL LIVE AIRCRAFT TRACKING SYSTEM</div>',
    unsafe_allow_html=True
)

st.divider()


# ==========================================
# FETCH OR REUSE DATA
# ==========================================

# A manual refresh always tries the API again.
# Otherwise, reuse the last successful data for 30 seconds.

should_fetch = (
    st.session_state.last_flight_data is None
    or st.session_state.force_refresh
)

if st.session_state.last_fetch_time is not None:
    age = (
        datetime.now(timezone.utc)
        - st.session_state.last_fetch_time
    ).total_seconds()

    if age >= 30:
        should_fetch = True

if should_fetch:
    with st.spinner("Connecting to OpenSky aircraft network..."):
        result = fetch_opensky()

    if result["data"] is not None:
        st.session_state.last_flight_data = result["data"]
        st.session_state.last_fetch_time = result["time"]
        st.session_state.api_error = None
    else:
        st.session_state.api_error = result["error"]


# ==========================================
# LOAD CURRENT OR LAST AVAILABLE DATA
# ==========================================

aircraft_df = st.session_state.last_flight_data

if aircraft_df is None:
    st.error(
        "Aircraft data is currently unavailable. "
        "The application could not connect to OpenSky."
    )

    st.warning(
        st.session_state.api_error
        or "Please try refreshing the aircraft data."
    )

    st.info(
        "Check again later. OpenSky's public aircraft feed "
        "may be temporarily unavailable."
    )

    st.stop()

if st.session_state.api_error:
    st.warning(
        "Live update failed. Showing the last successfully "
        "received aircraft data instead."
    )

    st.caption(
        f"Connection message: {st.session_state.api_error}"
    )

# Make a working copy.
df = aircraft_df.copy()

# Derived display columns.
df["Altitude (ft)"] = (
    pd.to_numeric(df["Altitude (m)"], errors="coerce") * 3.28084
)

df["Speed (km/h)"] = (
    pd.to_numeric(df["Speed (m/s)"], errors="coerce") * 3.6
)

df["Speed (knots)"] = (
    pd.to_numeric(df["Speed (m/s)"], errors="coerce") * 1.94384
)

df["Last Contact UTC"] = df["Last Contact"].apply(utc_time)
df["Position Time UTC"] = df["Time Position"].apply(utc_time)

fetch_time = st.session_state.last_fetch_time

if fetch_time:
    st.caption(
        "Last successful data update: "
        + fetch_time.strftime("%Y-%m-%d %H:%M:%S UTC")
    )


# ==========================================
# DASHBOARD METRICS
# ==========================================

total_aircraft = len(df)

airborne = 0
if total_aircraft:
    airborne = int((df["On Ground"] == False).sum())

countries = int(df["Country"].nunique())

col1, col2, col3 = st.columns(3)

col1.metric("AIRCRAFT WITH POSITIONS", f"{total_aircraft:,}")
col2.metric("AIRBORNE AIRCRAFT", f"{airborne:,}")
col3.metric("COUNTRIES", f"{countries:,}")

st.divider()


# ==========================================
# MAP FUNCTION
# ==========================================

def show_aircraft_map(map_df, height=650):

    if map_df.empty:
        st.info("No aircraft with map positions found.")
        return

    if len(map_df) > 5000:
        map_df = map_df.sample(5000, random_state=42)

    fig = px.scatter_map(
        map_df,
        lat="Latitude",
        lon="Longitude",
        hover_name="Callsign",
        hover_data={
            "ICAO24": True,
            "Country": True,
            "Altitude (ft)": ":.0f",
            "Speed (knots)": ":.1f",
            "Heading": True,
            "Latitude": False,
            "Longitude": False
        },
        zoom=1,
        height=height
    )

    fig.update_traces(
        marker={
            "size": 7,
            "color": "#29c7ff",
            "opacity": 0.85
        }
    )

    fig.update_layout(
        map_style="open-street-map",
        paper_bgcolor="#07111f",
        plot_bgcolor="#07111f",
        font_color="#eaf2ff",
        margin=dict(l=0, r=0, t=0, b=0)
    )

    st.plotly_chart(
        fig,
        use_container_width=True
    )


# ==========================================
# AIRCRAFT DETAILS
# ==========================================

def show_details(row):

    st.subheader("✈ Aircraft Information")

    def display_value(value, suffix=""):
        if pd.isna(value):
            return "Unavailable"

        if isinstance(value, float):
            return f"{value:.2f}{suffix}"

        return f"{value}{suffix}"

    details = [
        ("ICAO24", row.get("ICAO24")),
        ("Callsign", row.get("Callsign")),
        ("Origin Country", row.get("Country")),
        ("Longitude", display_value(row.get("Longitude"))),
        ("Latitude", display_value(row.get("Latitude"))),
        ("Altitude", display_value(row.get("Altitude (ft)"), " ft")),
        ("Geometric Altitude", display_value(
            pd.to_numeric(
                row.get("Geometric Altitude (m)"),
                errors="coerce"
            ) * 3.28084,
            " ft"
        )),
        ("Ground Speed", display_value(row.get("Speed (knots)"), " knots")),
        ("Speed", display_value(row.get("Speed (km/h)"), " km/h")),
        ("Heading", display_value(row.get("Heading"), "°")),
        ("Vertical Rate", display_value(row.get("Vertical Rate"), " m/s")),
        ("Squawk", display_value(row.get("Squawk"))),
        ("On Ground", display_value(row.get("On Ground"))),
        ("Position Time", row.get("Position Time UTC", "Unavailable")),
        ("Last Contact", row.get("Last Contact UTC", "Unavailable")),
        ("Position Source", display_value(row.get("Position Source"))),
        ("Category", display_value(row.get("Category")))
    ]

    left, right = st.columns(2)

    for index, (label, value) in enumerate(details):
        target = left if index % 2 == 0 else right

        with target:
            st.markdown(
                f"""
                <div class="info-card">
                    <div class="info-label">{label}</div>
                    <div class="info-value">{value}</div>
                </div>
                """,
                unsafe_allow_html=True
            )


# ==========================================
# FLIGHT SEARCH
# ==========================================

if page == "Flight Search":

    st.subheader("🔎 Search Aircraft")

    st.write(
        "Search using a flight callsign or ICAO24 aircraft address."
    )

    with st.form("flight_search_form"):
        query = st.text_input(
            "Flight number / Callsign / ICAO24",
            value=st.session_state.flight_query,
            placeholder="Example: BBC355 or ICAO24 address"
        )

        search_button = st.form_submit_button(
            "SEARCH FLIGHT",
            use_container_width=True
        )

    if search_button:
        st.session_state.flight_query = query.strip()

    search_query = st.session_state.flight_query.strip().upper()

    if search_query:

        search_terms = [search_query]

        # Biman Bangladesh IATA code BG -> ICAO callsign prefix BBC.
        if search_query.startswith("BG") and len(search_query) > 2:
            search_terms.append("BBC" + search_query[2:])

        matches = df[
            df["Callsign"].fillna("").str.upper().apply(
                lambda value: any(
                    term in value for term in search_terms
                )
            )
            |
            df["ICAO24"].fillna("").str.upper().str.contains(
                search_query,
                regex=False
            )
        ].copy()

        if not matches.empty:

            st.success(
                f"Found {len(matches)} matching aircraft."
            )

            show_aircraft_map(matches, height=500)

            if len(matches) > 1:

                options = matches.index.tolist()

                selected_index = st.selectbox(
                    "Select an aircraft",
                    options,
                    format_func=lambda index: (
                        str(matches.loc[index, "Callsign"])
                        + " | "
                        + str(matches.loc[index, "ICAO24"])
                    )
                )

                selected_aircraft = matches.loc[selected_index]

            else:
                selected_aircraft = matches.iloc[0]

            show_details(selected_aircraft)

        else:
            st.warning(
                "No matching aircraft found in the currently "
                "available OpenSky data."
            )

            st.info(
                "The aircraft may not currently be transmitting "
                "a visible position, or its callsign may be different."
            )

            st.caption(
                "Try searching again later or check the callsign."
            )

    else:
        st.info(
            "Enter a flight number or callsign above to search."
        )


# ==========================================
# WORLDWIDE MAP
# ==========================================

elif page == "Worldwide Map":

    st.subheader("🌍 Worldwide Aircraft Radar")

    st.write(
        "Aircraft positions currently available from the OpenSky network."
    )

    show_aircraft_map(df, height=700)

    st.caption(
        "Map positions depend on available ADS-B coverage. "
        "This is not a primary military or airport radar."
    )


# ==========================================
# AIRCRAFT DATABASE
# ==========================================

elif page == "Aircraft Database":

    st.subheader("📡 Aircraft Database")

    search_database = st.text_input(
        "Filter by callsign, ICAO24 or country",
        placeholder="Search aircraft..."
    )

    database = df.copy()

    if search_database.strip():

        term = search_database.strip().upper()

        database = database[
            database["Callsign"].fillna("").str.upper().str.contains(
                term, regex=False
            )
            |
            database["ICAO24"].fillna("").str.upper().str.contains(
                term, regex=False
            )
            |
            database["Country"].fillna("").str.upper().str.contains(
                term, regex=False
            )
        ]

    visible_columns = [
        "Callsign",
        "ICAO24",
        "Country",
        "Latitude",
        "Longitude",
        "Altitude (ft)",
        "Speed (knots)",
        "Heading",
        "On Ground",
        "Squawk"
    ]

    st.dataframe(
        database[visible_columns],
        use_container_width=True,
        hide_index=True
    )

    st.caption(
        f"Showing {len(database):,} aircraft records with known positions."
    )


# ==========================================
# ABOUT
# ==========================================

elif page == "About":

    st.subheader("About PLAN RADAR X")

    st.markdown("""
    **PLAN RADAR X** is a worldwide aircraft tracking dashboard.

    ### Features

    - Worldwide aircraft map
    - Flight callsign search
    - ICAO24 search
    - Aircraft information
    - Aircraft database
    - Automatic refresh
    - API retry and timeout handling
    - Last successful data fallback

    ### Data Source

    Aircraft state information is retrieved from the
    OpenSky Network public API.

    ### Important Limitations

    - Aircraft coverage depends on available ADS-B receivers.
    - Some aircraft may not appear.
    - Departure and destination information is not supplied
      by the states/all endpoint.
    - Aircraft model and historical route information may
      not be available.
    - This application is not a primary radar system.
    - Public API access may have rate limits or temporary outages.

    **PLAN RADAR X — Global Aircraft Tracking**
    """)
