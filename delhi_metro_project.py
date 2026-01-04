import streamlit as st
import pandas as pd
import networkx as nx
from geopy.distance import geodesic
import os

# ---------------- PAGE CONFIG ----------------
st.set_page_config(page_title="Delhi Metro Route Finder", layout="wide")

# ---------------- CSS ----------------
st.markdown("""
<style>
.block-container { max-width:1100px; padding-top:1.2rem; }

.route-box {
    background:#0f172a;
    color:white;
    padding:12px 16px;
    border-radius:10px;
    margin-bottom:6px;
    border-left:5px solid #38bdf8;
}

.junction-box {
    margin-left:26px;
    margin-bottom:14px;
    color:#facc15;
    font-size:14px;
}

.footer {
    text-align:center;
    color:#94a3b8;
    margin-top:40px;
    font-size:14px;
}
</style>
""", unsafe_allow_html=True)

# ---------------- LINE NAME MAP ----------------
LINE_NAME_MAP = {
    "B_DN_R": "Blue Line",
    "B_DV_R": "Blue Line",
    "Y_QV_R": "Yellow Line",
    "R_RD_R": "Red Line",
    "P_MS_R": "Pink Line",
    "V_KR_R": "Violet Line",
    "M_JB_R": "Magenta Line",
    "G_KB_R": "Green Line",
    "A_NN_R": "Aqua Line",
    "O_DN_R": "Airport Express Line"
}

def friendly_line(code):
    return LINE_NAME_MAP.get(code, code)

# ---------------- DMRC FARE ----------------
def dmrc_fare(dist):
    if dist <= 2: return 11
    if dist <= 5: return 21
    if dist <= 12: return 32
    if dist <= 21: return 43
    if dist <= 32: return 54
    return 64

# ---------------- LOAD DATA ----------------
@st.cache_data
def load_data():
    sm = pd.read_excel("data/stations_master.xlsx")
    lm = pd.read_csv("data/station_line_mapping.csv")
    ed = pd.read_csv("data/edges_table.csv")

    for df in [sm, lm, ed]:
        df.columns = df.columns.str.lower().str.strip()

    lm = lm.merge(
        sm[["station_name","latitude","longitude"]],
        on="station_name",
        how="left"
    )
    return lm, ed

stations, edges = load_data()

# ---------------- HELPERS ----------------
def get_line_terminals(line):
    df = stations[stations["line_name"] == line].sort_values("sequence_order")
    if df.empty:
        return None, None
    return df.iloc[0]["station_name"], df.iloc[-1]["station_name"]

def get_direction(curr, nxt, line):
    df = stations[stations["line_name"] == line]
    c = df[df["station_name"] == curr]["sequence_order"].values
    n = df[df["station_name"] == nxt]["sequence_order"].values
    if len(c)==0 or len(n)==0:
        return None
    start, end = get_line_terminals(line)
    return f"Towards {end}" if n[0] > c[0] else f"Towards {start}"

# ---------------- GRAPH ----------------
G = nx.Graph()
for _, r in stations.iterrows():
    G.add_node(
        r["station_name"],
        lat=r["latitude"],
        lon=r["longitude"]
    )

for _, r in edges.iterrows():
    G.add_edge(
        r["from_station"],
        r["to_station"],
        weight=float(r.get("travel_time_min", 2)),
        line=r["line_name"]
    )

# ---------------- HEADER ----------------
h1, h2 = st.columns([6,1])
with h1:
    st.title("🚇 Delhi Metro Route Finder")
with h2:
    st.markdown("<div style='height:38px'></div>", unsafe_allow_html=True)
    if st.button("🗺 View Map"):
        st.session_state.show_map = not st.session_state.get("show_map", False)

# ---------------- INPUTS (NO PREFILLED STATION) ----------------
station_list = ["-- Select Station --"] + sorted(G.nodes)

source = st.selectbox("🚉 Source Station", station_list, index=0)
target = st.selectbox("🎯 Destination Station", station_list, index=0)

# ---------------- MAP ----------------
if st.session_state.get("show_map", False):
    st.image("data/Delhi_metro_map.png", use_container_width=True)
    st.markdown("---")

# ---------------- ROUTE ----------------
if st.button("🚆 Get Route"):

    if source == "-- Select Station --" or target == "-- Select Station --":
        st.warning("⚠️ Please select both Source and Destination stations")
        st.stop()

    path = nx.shortest_path(G, source, target, weight="weight")

    # distance
    distance = 0
    for i in range(len(path)-1):
        distance += geodesic(
            (G.nodes[path[i]]["lat"], G.nodes[path[i]]["lon"]),
            (G.nodes[path[i+1]]["lat"], G.nodes[path[i+1]]["lon"])
        ).km

    fare = dmrc_fare(distance)
    est_time = int((distance/35)*60 + len(path)*0.4)

    # ---------------- SUMMARY ----------------
    st.markdown(f"""
    <div style="background:#0e2a47;padding:16px;border-radius:14px;color:white">
    <h3>🚇 Route Summary</h3>
    ⏱ {est_time} min &nbsp;&nbsp; ₹ {fare} &nbsp;&nbsp; 🚉 {len(path)} Stations
    <br><br>
    <b>From:</b> {source}<br>
    <b>To:</b> {target}
    </div>
    """, unsafe_allow_html=True)

    # ---------------- DETAILS ----------------
    st.markdown("## 🧭 Route Details")
    prev_line = None

    for i, s in enumerate(path, start=1):
        st.markdown(f"<div class='route-box'><b>{i}. {s}</b></div>", unsafe_allow_html=True)

        if i < len(path):
            curr = path[i-1]
            nxt = path[i]
            line = G[curr][nxt]["line"]
            direction = get_direction(curr, nxt, line)

            if prev_line and prev_line != line:
                st.markdown(
                    f"""
                    <div class='junction-box'>
                    🔁 <b>Junction</b><br>
                    Change from {friendly_line(prev_line)} to {friendly_line(line)}<br>
                    <i>{direction}</i>
                    </div>
                    """,
                    unsafe_allow_html=True
                )
            prev_line = line

# ---------------- FOOTER ----------------
st.markdown("""
<div class="footer">
Developed with ❤️ by <b>Akash Sharma</b>
</div>
""", unsafe_allow_html=True)
