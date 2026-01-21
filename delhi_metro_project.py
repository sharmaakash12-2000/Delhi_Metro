import streamlit as st
import pandas as pd
import networkx as nx
from geopy.distance import geodesic

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
    border-left:6px solid var(--line-color);
}

.junction-box {
    margin-left:26px;
    margin-bottom:14px;
    color:#facc15;
    font-size:14px;
}

.badge {
    display:inline-block;
    padding:6px 12px;
    border-radius:18px;
    font-size:13px;
    margin-right:6px;
}

.footer {
    text-align:center;
    color:#94a3b8;
    margin-top:40px;
    font-size:14px;
}
</style>
""", unsafe_allow_html=True)

# ---------------- LINE INFO ----------------
LINE_INFO = {
    "B_DN_R": {"name": "Blue Line", "color": "#1e88e5"},
    "B_DV_R": {"name": "Blue Line", "color": "#1e88e5"},
    "Y_QV_R": {"name": "Yellow Line", "color": "#facc15"},
    "R_RS_R":   {"name": "Red Line", "color": "#ef4444"},
    "R_RD":   {"name": "Red Line", "color": "#ef4444"},
    "P_MS":   {"name": "Pink Line", "color": "#ec4899"},
    "P_MS_R": {"name": "Pink Line", "color": "#ec4899"},
    "V_KR":   {"name": "Violet Line", "color": "#8b5cf6"},
    "V_KR_R": {"name": "Violet Line", "color": "#8b5cf6"},
    "M_JB":   {"name": "Magenta Line", "color": "#d946ef"},
    "M_JB_R":   {"name": "Magenta Line", "color": "#d946ef"},
    "G_KB":   {"name": "Green Line", "color": "#22c55e"},
    "A_NN":   {"name": "Aqua Line", "color": "#06b6d4"},
    "O_DN":   {"name": "Airport Express", "color": "#f97316"}
}

def line_name(code):
    return LINE_INFO.get(code, {}).get("name", code)

def line_color(code):
    return LINE_INFO.get(code, {}).get("color", "#38bdf8")

# ---------------- PLATFORM RULES ----------------
PLATFORM_RULES = {
    "B_DN_R": {"forward": 2, "reverse": 1},
    "B_DV_R": {"forward": 2, "reverse": 1},
    "Y_QV_R": {"forward": 2, "reverse": 1},
    "R_RD":   {"forward": 1, "reverse": 2},
    "P_MS":   {"forward": 3, "reverse": 4},
    "P_MS_R": {"forward": 3, "reverse": 4},
    "V_KR":   {"forward": 2, "reverse": 1},
    "V_KR_R": {"forward": 2, "reverse": 1},
    "M_JB":   {"forward": 2, "reverse": 1},
    "G_KB":   {"forward": 1, "reverse": 2},
    "A_NN":   {"forward": 2, "reverse": 1},
    "O_DN":   {"forward": 3, "reverse": 1},
}

def get_platform(line_code, direction):
    return f"Platform {PLATFORM_RULES.get(line_code, {}).get(direction, 1)}"

# ---------------- FARE ----------------
def dmrc_fare(dist):
    if dist <= 2: return 11
    if dist <= 5: return 21
    if dist <= 12: return 32
    if dist <= 21: return 43
    if dist <= 32: return 54
    return 64

# ---------------- TIME ----------------
BASE_SPEED = 28
DWELL = 0.8
INTERCHANGE = 4

def calculate_time(dist, stations, changes):
    travel = (dist / BASE_SPEED) * 60
    return int(round(travel + stations * DWELL + changes * INTERCHANGE))

# ---------------- LOAD DATA ----------------
@st.cache_data
def load_data():
    sm = pd.read_excel("data/stations_master.xlsx")
    lm = pd.read_csv("data/station_line_mapping.csv")
    ed = pd.read_csv("data/edges_table.csv")

    for df in [sm, lm, ed]:
        df.columns = df.columns.str.lower().str.strip()

    lm = lm.merge(
        sm[["station_name", "latitude", "longitude"]],
        on="station_name",
        how="left"
    )
    return lm, ed

stations, edges = load_data()

# ---------------- DIRECTION + PLATFORM ----------------
def get_boarding_info(curr, nxt, line):
    df = stations[stations["line_name"] == line]
    c = df[df["station_name"] == curr]["sequence_order"].values
    n = df[df["station_name"] == nxt]["sequence_order"].values

    if len(c) == 0 or len(n) == 0:
        return "Towards terminal", "Platform 1"

    start = df.sort_values("sequence_order").iloc[0]["station_name"]
    end   = df.sort_values("sequence_order").iloc[-1]["station_name"]

    if n[0] > c[0]:
        return f"Towards {end}", get_platform(line, "forward")
    else:
        return f"Towards {start}", get_platform(line, "reverse")

# ---------------- GRAPH ----------------
G = nx.Graph()
for _, r in stations.iterrows():
    G.add_node(r["station_name"], lat=r["latitude"], lon=r["longitude"])

for _, r in edges.iterrows():
    G.add_edge(
        r["from_station"],
        r["to_station"],
        weight=float(r.get("travel_time_min", 2)),
        line=r["line_name"]
    )

# ---------------- HEADER + MAP ----------------
if "show_map" not in st.session_state:
    st.session_state.show_map = False

h1, h2 = st.columns([6,1])
with h1:
    st.title("🚇 Delhi Metro Route Finder")
with h2:
    st.markdown("<div style='height:38px'></div>", unsafe_allow_html=True)
    if st.button("🗺 View Map"):
        st.session_state.show_map = not st.session_state.show_map

if st.session_state.show_map:
    st.image("data/Delhi_metro_map.png", use_container_width=True)
    st.markdown("---")

# ---------------- INPUTS ----------------
source = st.selectbox("🚉 Source Station", sorted(G.nodes), index=None, placeholder="Search station...")
target = st.selectbox("🎯 Destination Station", sorted(G.nodes), index=None, placeholder="Search station...")

# ---------------- ROUTE ----------------
if st.button("🚆 Get Route") and source and target:
    path = nx.shortest_path(G, source, target, weight="weight")

    distance = sum(
        geodesic(
            (G.nodes[path[i]]["lat"], G.nodes[path[i]]["lon"]),
            (G.nodes[path[i+1]]["lat"], G.nodes[path[i+1]]["lon"])
        ).km
        for i in range(len(path)-1)
    )

    prev = None
    changes = 0
    for i in range(len(path)-1):
        l = G[path[i]][path[i+1]]["line"]
        if prev and prev != l:
            changes += 1
        prev = l

    fare = dmrc_fare(distance)
    time = calculate_time(distance, len(path), changes)

    # ---------------- SUMMARY ----------------
    st.markdown(f"""
    <div style="background:#0e2a47;padding:18px;border-radius:14px;color:white">
    <h3>🚇 Route Summary</h3>
    <span class="badge" style="background:#1e88e5">⏱ {time} min</span>
    <span class="badge" style="background:#22c55e">₹ {fare}</span>
    <span class="badge" style="background:#9333ea">🚉 {len(path)} Stations</span>
    <span class="badge" style="background:#f59e0b">🔁 {changes} Change</span>
    <br><br>
    <b>From:</b> {source}<br>
    <b>To:</b> {target}
    </div>
    """, unsafe_allow_html=True)

    # ---------------- DETAILS ----------------
    st.markdown("## 🧭 Route Details")

    first_line = G[path[0]][path[1]]["line"]
    direction, platform = get_boarding_info(path[0], path[1], first_line)

    st.markdown(
        f"""
        <div style="margin:12px 0 18px 14px;color:#38bdf8">
        🚇 <b>Board {line_name(first_line)}</b><br>
        ➡ {direction}<br>
        🚉 {platform}
        </div>
        """,
        unsafe_allow_html=True
    )

    prev_line = first_line

    for i, s in enumerate(path, start=1):
        line = None
        if i < len(path):
            line = G[path[i-1]][path[i]]["line"]

        st.markdown(
            f"<div class='route-box' style='--line-color:{line_color(line)}'><b>{i}. {s}</b></div>",
            unsafe_allow_html=True
        )

        if prev_line and line and prev_line != line:
            direction, platform = get_boarding_info(path[i-1], path[i], line)
            st.markdown(
                f"""
                <div class='junction-box'>
                🔁 <b>Junction</b><br>
                Change from {line_name(prev_line)} to {line_name(line)}<br>
                ➡ {direction}<br>
                🚉 {platform}
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
