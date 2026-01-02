import streamlit as st
import pandas as pd
import networkx as nx
from geopy.distance import geodesic

# --- Load CSVs safely and merge coordinates ---
@st.cache_data
def load_data():
    # Try loading all three files (station_master optional but recommended)
    try:
        station_master = pd.read_csv("station_master.csv")
    except FileNotFoundError:
        station_master = None

    try:
        station_lines = pd.read_csv("D:\DMS-main\data\station_line_mapping.csv")
    except FileNotFoundError:
        st.error("station_line_mapping.csv not found in working folder.")
        st.stop()

    try:
        edges = pd.read_csv("D:\DMS-main\data\edges_table.csv")
    except FileNotFoundError:
        st.error("edges_table.csv not found in working folder.")
        st.stop()

    # Normalize column names: strip + lower
    def clean_cols(df):
        df.columns = df.columns.str.strip().str.lower()
        return df

    station_lines = clean_cols(station_lines)
    edges = clean_cols(edges)
    if station_master is not None:
        station_master = clean_cols(station_master)

    # Standardize common column names if variants exist
    station_lines.rename(columns={
        'station id': 'station_id',
        'station id ': 'station_id',
        'station_name': 'station_name',  # keep if already OK
        'station name': 'station_name',
        'station': 'station_name',
        'line name': 'line_name',
        'line': 'line_name',
        'sequence order': 'sequence_order',
        'sequence_order': 'sequence_order'
    }, inplace=True)

    edges.rename(columns={
        'from': 'from_station',
        'source': 'from_station',
        'from_station': 'from_station',
        'to': 'to_station',
        'destination': 'to_station',
        'to_station': 'to_station',
        'line name': 'line_name',
        'line': 'line_name',
        'travel_time_min': 'travel_time_min',
        'travel time min': 'travel_time_min'
    }, inplace=True)

    if station_master is not None:
        station_master.rename(columns={
            'station id': 'station_id',
            'station name': 'station_name',
            'station_name': 'station_name',
            'lat': 'latitude',
            'latitude': 'latitude',
            'lon': 'longitude',
            'lng': 'longitude',
            'longitude': 'longitude'
        }, inplace=True)

    # Merge coords into station_lines if station_master present
    if station_master is not None and 'station_name' in station_master.columns:
        # keep only station_name, latitude, longitude from master (if they exist)
        cols_to_take = []
        if 'station_name' in station_master.columns:
            cols_to_take.append('station_name')
        if 'latitude' in station_master.columns:
            cols_to_take.append('latitude')
        if 'longitude' in station_master.columns:
            cols_to_take.append('longitude')

        if 'latitude' in station_master.columns and 'longitude' in station_master.columns:
            station_lines = station_lines.merge(
                station_master[cols_to_take].drop_duplicates(subset=['station_name']),
                on='station_name',
                how='left'
            )

    return station_lines, edges

# --- Load Data ---
stations, edges = load_data()

# Debug prints (uncomment temporarily if you want to see columns in console)
# print("STATIONS COLUMNS:", stations.columns.tolist())
# print("EDGES COLUMNS:", edges.columns.tolist())

# --- Column mapping (standard lowercase names) ---
station_col = "station_name"
lat_col = "latitude"
lon_col = "longitude"
line_col = "line_name"
source_col = "from_station"
target_col = "to_station"
time_col = "travel_time_min"

# --- Validate required columns presence (but allow missing lat/lon if edges have travel times) ---
missing_required = []
for c in [station_col, line_col, source_col, target_col]:
    if c not in stations.columns and c not in edges.columns:
        missing_required.append(c)

# Edges must have from/to
if source_col not in edges.columns or target_col not in edges.columns:
    st.error("❌ edges_table.csv must contain From/To station columns. Check column names.")
    st.stop()

# Stations must have station_name
if station_col not in stations.columns:
    st.error("❌ station_line_mapping.csv must contain Station_Name column. Check column names.")
    st.stop()

# --- Parameters ---
INTERCHANGE_TIME = 1  # minutes extra for line change
DWELL_TIME = 0.2      # minutes per station
AVG_SPEED_KMH = 80    # average metro speed
DEFAULT_EDGE_TIME = 2  # fallback minutes if nothing else available

# Helper: try to get travel_time from edges table (symmetric search)
def get_edge_travel_time(a, b):
    # look for a->b or b->a
    mask = ((edges[source_col] == a) & (edges[target_col] == b)) | ((edges[source_col] == b) & (edges[target_col] == a))
    rows = edges[mask]
    if not rows.empty:
        # prefer numeric travel_time_min column if present
        if time_col in rows.columns:
            val = rows.iloc[0][time_col]
            try:
                return float(val)
            except Exception:
                return DEFAULT_EDGE_TIME
        else:
            return DEFAULT_EDGE_TIME
    return None

# --- Function to calculate travel time (robust) ---
def calculate_travel_time(from_station, to_station):
    # 1) Prefer explicit travel time in edges_table if present
    t = get_edge_travel_time(from_station, to_station)
    if t is not None:
        return t

    # 2) If coordinates present in stations dataframe, use geodesic
    try:
        if lat_col in stations.columns and lon_col in stations.columns:
            lat1 = stations.loc[stations[station_col] == from_station, lat_col].values
            lon1 = stations.loc[stations[station_col] == from_station, lon_col].values
            lat2 = stations.loc[stations[station_col] == to_station, lat_col].values
            lon2 = stations.loc[stations[station_col] == to_station, lon_col].values
            if lat1.size and lon1.size and lat2.size and lon2.size:
                distance_km = geodesic((float(lat1[0]), float(lon1[0])), (float(lat2[0]), float(lon2[0]))).km
                return distance_km / AVG_SPEED_KMH * 60
    except Exception:
        pass

    # 3) Last resort fallback
    return DEFAULT_EDGE_TIME

# --- Check for missing stations in mapping vs edges (warn) ---
missing_stations = set(edges[source_col].unique()).union(set(edges[target_col].unique())) - set(stations[station_col].unique())
if missing_stations:
    st.warning(f"⚠️ Missing stations in station_line_mapping.csv (these appear in edges_table): {missing_stations}")

# --- Build Graph dynamically ---
G = nx.Graph()
for _, row in stations.iterrows():
    node_name = row[station_col]
    # attach line info if available
    attrs = {}
    if line_col in stations.columns:
        attrs['line'] = row.get(line_col)
    G.add_node(node_name, **attrs)

for _, row in edges.iterrows():
    a = row[source_col]
    b = row[target_col]
    edge_line = row.get(line_col) if line_col in row.index else None
    # weight: prefer explicit travel_time_min from edges, else calculate
    edge_time = None
    if time_col in edges.columns:
        try:
            v = row[time_col]
            edge_time = float(v)
        except Exception:
            edge_time = None
    if edge_time is None:
        edge_time = calculate_travel_time(a, b)

    # Use edge_line from edges first, fallback to nodes' line if available
    line_value = edge_line if edge_line is not None else (stations.loc[stations[station_col] == a, line_col].values[0] if line_col in stations.columns and not stations.loc[stations[station_col] == a].empty else None)

    G.add_edge(a, b, weight=edge_time, line=line_value)

# --- Streamlit UI ---
st.title("🚇 Delhi Metro Route Finder")

# protect if graph nodes empty
if len(G.nodes) == 0:
    st.error("Graph has no stations. Check your CSVs.")
    st.stop()

source = st.selectbox("Select Source Station", sorted(list(G.nodes())))
target = st.selectbox("Select Destination Station", sorted(list(G.nodes())))

if st.button("Get Route"):
    try:
        path = nx.shortest_path(G, source=source, target=target, weight="weight")
        route_steps = []
        total_time = 0.0
        prev_line = None
        last_change_station = None

        for i in range(len(path) - 1):
            current = path[i]
            nxt = path[i + 1]

            edge_data = G[current][nxt]
            raw_line = edge_data.get("line") or ""
            edge_line = str(raw_line).strip().lower()
            edge_time = edge_data.get("weight", DEFAULT_EDGE_TIME) or DEFAULT_EDGE_TIME

            total_time += float(edge_time) + DWELL_TIME

            # Detect interchange only when line truly changes (and not already changed at same station)
            if prev_line and prev_line != edge_line and last_change_station != current:
                route_steps.append(
                    f"➡️ Change from **{prev_line.title()} Line** to **{raw_line.title() if isinstance(raw_line,str) else raw_line} Line** at **{current}**"
                )
                total_time += INTERCHANGE_TIME
                last_change_station = current

            # Add travel step
            route_steps.append(f"🚇 Go to **{nxt}** ({raw_line if raw_line else 'Unknown'} Line)")
            prev_line = edge_line

        # --- Output ---

        # Count total stations (including source & destination)
        total_stations = len(path)

        st.info(f"📍 Total Stations: **{total_stations}**")

        st.success(f"Fastest route from **{source}** to **{target}**:")
        for step in route_steps:
            st.write(step)

        st.metric(label="Estimated Travel Time", value=f"{int(total_time)} min")

    except Exception as e:
        st.error(f"❌ No route found between selected stations. Error: {e}")

#jdjjd
# x=10
# y=x
# x+=5
# print(y)
