# PLAN RADAR X

PLAN RADAR X is a Streamlit-based live aircraft tracking dashboard that pulls real-time flight data from the OpenSky Network API and displays it on a worldwide aircraft map.

## Features

- Live aircraft tracking map
- Search by flight number, callsign, or ICAO24 code
- Aircraft details panel
- Country filtering
- Status filtering (Airborne / On Ground)
- CSV export
- Auto-refresh support

## Tech Stack

- Python
- Streamlit
- Pandas
- Plotly
- OpenSky Network API

## Project Structure

- `app.py` - Main Streamlit application
- `requirements.txt` - Python dependencies

## Run Locally

1. Clone the repository:

   ```bash
   git clone https://github.com/Apan2026/PLAN-RADAR-X.git
   cd PLAN-RADAR-X
   ```

2. Create and activate a virtual environment (optional but recommended):

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```

3. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

4. Start the app:

   ```bash
   streamlit run app.py
   ```

5. Open the local URL shown in the terminal, usually:

   ```text
   http://localhost:8501
   ```

## Data Source

This app uses the OpenSky Network ADS-B API for live aircraft state data.

## Notes

- This project displays aircraft data that is available from the public OpenSky API.
- Exact flight history, departure/destination, and aircraft model are not included in the API response.
- Availability depends on ADS-B coverage and the live data feed.

## Author

Created by Apan2026.
