import os
from datetime import datetime, date, timedelta

import pandas as pd
import plotly.express as px
import streamlit as st

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------
st.set_page_config(layout="wide", page_title="NNJA vs ERA5 DA Daily Overlap")

DATA_CSV_CANDIDATES = [
    "nnja_era5_daily_comparison_inventory.csv",
    os.path.join("nnja_era5_daily_comparison", "nnja_era5_daily_comparison_inventory.csv"),
    "/mnt/data/nnja_era5_daily_comparison/nnja_era5_daily_comparison_inventory.csv",
]
DATA_XLSX_CANDIDATES = [
    "nnja_era5_daily_comparison.xlsx",
    os.path.join("nnja_era5_daily_comparison", "nnja_era5_daily_comparison.xlsx"),
    "/mnt/data/nnja_era5_daily_comparison/nnja_era5_daily_comparison.xlsx",
]

STATUS_COLOR_MAP = {
    "Both": "#2ca02c",
    "Both + ERA-Interim-only marker": "#167a3a",
    "NNJA Only": "#F59E0B",
    "NNJA + ERA-Interim-only (not ERA5)": "#D97706",
    "ERA5 Only": "#4275ed",
    "ERA-Interim Only (not ERA5)": "#D62728",
}

STATUS_ORDER = [
    "Both",
    "Both + ERA-Interim-only marker",
    "NNJA Only",
    "NNJA + ERA-Interim-only (not ERA5)",
    "ERA5 Only",
    "ERA-Interim Only (not ERA5)",
]

# Fixed 365-day calendar used by the extraction workflow.
MONTH_LENGTHS_365 = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]


def to_no_leap_doy(d: date) -> int:
    """Convert a normal date to the D001-D365 calendar used in the CSV."""
    day = d.day
    if d.month == 2 and d.day == 29:
        # The source calendar has no leap day. Map Feb 29 to Feb 28's bin.
        day = 28
    return sum(MONTH_LENGTHS_365[: d.month - 1]) + day


def no_leap_abs_day(d: date, base_year: int) -> int:
    return (d.year - base_year) * 365 + to_no_leap_doy(d)


@st.cache_data(show_spinner=False)
def locate_data_file() -> tuple[str, str]:
    for p in DATA_CSV_CANDIDATES:
        if os.path.exists(p):
            return p, "csv"
    for p in DATA_XLSX_CANDIDATES:
        if os.path.exists(p):
            return p, "xlsx"
    raise FileNotFoundError(
        "Could not find nnja_era5_daily_comparison_inventory.csv or "
        "nnja_era5_daily_comparison.xlsx. Put the data file beside app.py."
    )


@st.cache_data(show_spinner=True)
def load_data() -> pd.DataFrame:
    path, kind = locate_data_file()
    if kind == "csv":
        df = pd.read_csv(path)
    else:
        df = pd.read_excel(path, sheet_name="Comparison_Segments")

    # Parse daily interval endpoints. End_Date is inclusive in the data file.
    df["Start_Date"] = pd.to_datetime(df["Start_Date"])
    df["End_Date"] = pd.to_datetime(df["End_Date"])

    # Robust booleans for data read from CSV or Excel.
    for col in ["NNJA_Active", "ERA5_DA_Active", "ERA_Interim_Only_Active"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.lower().isin(["true", "1", "yes"])

    # Ensure expected columns exist even if an edited file is supplied.
    defaults = {
        "Section": "Unknown",
        "Sensor": "Unknown",
        "Satellite": "Unknown",
        "Status": "Unknown",
        "Comparison_Status": "Unknown",
        "NNJA_Codes": "",
        "ERA5_Codes": "",
        "ERA_Interim_Only_Codes": "",
        "NNJA_Source_Labels": "",
        "ERA_Source_Labels": "",
    }
    for col, default in defaults.items():
        if col not in df.columns:
            df[col] = default

    # Remove exact duplicates defensively. The build script already does this.
    dedupe_cols = [
        "Match_Key",
        "Start_Abs_Day_365",
        "End_Abs_Day_365",
        "Status",
        "NNJA_Codes",
        "ERA5_Codes",
        "ERA_Interim_Only_Codes",
    ]
    available_cols = [c for c in dedupe_cols if c in df.columns]
    if available_cols:
        df = df.drop_duplicates(subset=available_cols)

    return df


# -----------------------------------------------------------------------------
# Page header
# -----------------------------------------------------------------------------
st.title("🛰️ NNJA vs ERA5 DA: daily overlap from pixel-derived timelines")
st.markdown(
    "This dashboard compares the pixel-extracted NNJA inventory against ERA5 data-assimilation "
    "usage on a **D001-D365 daily grid**. ERA grey/green/blue bars are treated as ERA5 DA active; "
    "ERA red bars are kept separately as **ERA-Interim only, not ERA5**."
)

try:
    df = load_data()
except FileNotFoundError as exc:
    st.error(str(exc))
    st.stop()

base_year = int(df["Start_Date"].dt.year.min())
min_date = df["Start_Date"].min().to_pydatetime()
max_date = df["End_Date"].max().to_pydatetime()

# -----------------------------------------------------------------------------
# Sidebar controls
# -----------------------------------------------------------------------------
st.sidebar.header("Temporal filter")
st.sidebar.caption("Intervals are inclusive. One-day pixel markers are displayed with a one-day width.")
selected_dates = st.sidebar.slider(
    "Observation period",
    min_value=min_date,
    max_value=max_date,
    value=(min_date, max_date),
    format="YYYY-MM-DD",
)
selected_start, selected_end = selected_dates

st.sidebar.header("Comparison filters")
focus_overlap = st.sidebar.checkbox("Only show NNJA ∩ ERA5 DA overlap", value=False)
include_erai_only = st.sidebar.checkbox("Include ERA-Interim-only red segments", value=True)

available_statuses = [s for s in STATUS_ORDER if s in set(df["Status"].dropna())]
if not include_erai_only:
    available_statuses = [s for s in available_statuses if "ERA-Interim" not in s]
if focus_overlap:
    default_statuses = [s for s in available_statuses if s.startswith("Both")]
else:
    default_statuses = available_statuses
selected_statuses = st.sidebar.multiselect("Detailed status", available_statuses, default=default_statuses)

sections = sorted(df["Section"].dropna().unique())
selected_sections = st.sidebar.multiselect("Section", sections, default=sections)

sensors = sorted(df["Sensor"].dropna().unique())
selected_sensors = st.sidebar.multiselect("Sensor", sensors, default=sensors)

search_text = st.sidebar.text_input("Search item", value="", placeholder="e.g., AMSUA, NOAA 15, METOP-B")

# -----------------------------------------------------------------------------
# Filter and clip intervals
# -----------------------------------------------------------------------------
mask = (df["Start_Date"] <= selected_end) & (df["End_Date"] >= selected_start)
mask &= df["Status"].isin(selected_statuses)
mask &= df["Section"].isin(selected_sections)
mask &= df["Sensor"].isin(selected_sensors)
if focus_overlap:
    mask &= df["Comparison_Status"].eq("Both")
if search_text.strip():
    q = search_text.strip().casefold()
    text_cols = ["Sensor_Sat", "Sensor", "Satellite", "Match_Key", "NNJA_Source_Labels", "ERA_Source_Labels"]
    text_mask = False
    for col in text_cols:
        text_mask = text_mask | df[col].fillna("").astype(str).str.casefold().str.contains(q, regex=False)
    mask &= text_mask

filtered_df = df[mask].copy()

if filtered_df.empty:
    st.warning("No matched observation intervals are available for the selected filters.")
    st.stop()

filtered_df["Plot_Start"] = filtered_df["Start_Date"].clip(lower=selected_start)
filtered_df["Plot_End_Inclusive"] = filtered_df["End_Date"].clip(upper=selected_end)
filtered_df["Plot_End"] = filtered_df["Plot_End_Inclusive"] + pd.Timedelta(days=1)
filtered_df["Selected_Duration_Days"] = (
    filtered_df["Plot_End_Inclusive"] - filtered_df["Plot_Start"]
).dt.days + 1
filtered_df = filtered_df[filtered_df["Selected_Duration_Days"] > 0].copy()

# Defensively avoid duplicate visual rows.
visual_dedupe_cols = [
    "Sensor_Sat",
    "Plot_Start",
    "Plot_End_Inclusive",
    "Status",
    "NNJA_Codes",
    "ERA5_Codes",
    "ERA_Interim_Only_Codes",
]
filtered_df = filtered_df.drop_duplicates(subset=[c for c in visual_dedupe_cols if c in filtered_df.columns])

# -----------------------------------------------------------------------------
# KPI row
# -----------------------------------------------------------------------------
status_day_counts = (
    filtered_df.groupby("Comparison_Status", dropna=False)["Selected_Duration_Days"].sum().sort_values(ascending=False)
)
unique_items = filtered_df["Match_Key"].nunique()
both_items = filtered_df.loc[filtered_df["Comparison_Status"].eq("Both"), "Match_Key"].nunique()

k1, k2, k3, k4 = st.columns(4)
k1.metric("Visible intervals", f"{len(filtered_df):,}")
k2.metric("Unique sensor/satellite items", f"{unique_items:,}")
k3.metric("Items with NNJA ∩ ERA5 overlap", f"{both_items:,}")
k4.metric("Selected item-days", f"{int(filtered_df['Selected_Duration_Days'].sum()):,}")

with st.expander("Status day counts in selected interval", expanded=False):
    st.dataframe(status_day_counts.rename("item_days").reset_index(), use_container_width=True)

# -----------------------------------------------------------------------------
# Timeline
# -----------------------------------------------------------------------------
plot_df = filtered_df.sort_values(["Section", "Sensor", "Satellite", "Plot_Start", "Status"])
y_order = list(dict.fromkeys(plot_df["Sensor_Sat"].tolist()))

fig = px.timeline(
    plot_df,
    x_start="Plot_Start",
    x_end="Plot_End",
    y="Sensor_Sat",
    color="Status",
    color_discrete_map=STATUS_COLOR_MAP,
    category_orders={"Sensor_Sat": y_order},
    hover_data={
        "Section": True,
        "Sensor": True,
        "Satellite": True,
        "Start_Day_Label": True,
        "End_Day_Label": True,
        "Selected_Duration_Days": True,
        "NNJA_Codes": True,
        "ERA5_Codes": True,
        "ERA_Interim_Only_Codes": True,
        "NNJA_Source_Labels": True,
        "ERA_Source_Labels": True,
        "Plot_Start": False,
        "Plot_End": False,
    },
)
fig.update_yaxes(autorange="reversed")
fig.update_layout(
    height=min(1800, max(520, 24 * len(y_order) + 180)),
    xaxis_title="Daily timeline, 365-day no-leap calendar",
    yaxis_title="Normalized sensor / satellite item",
    legend_title="Detailed status",
    font=dict(size=12),
    margin=dict(l=10, r=10, t=40, b=20),
)
st.plotly_chart(fig, use_container_width=True)

# -----------------------------------------------------------------------------
# Overlap summary and detailed table
# -----------------------------------------------------------------------------
st.subheader("NNJA ∩ ERA5 DA overlap summary")
both_df = filtered_df[filtered_df["Comparison_Status"].eq("Both")].copy()
if both_df.empty:
    st.info("No NNJA ∩ ERA5 DA overlap appears in this selected interval.")
else:
    overlap_summary = (
        both_df.groupby(["Sensor_Sat", "Sensor", "Satellite", "Section"], dropna=False)
        .agg(
            overlap_days=("Selected_Duration_Days", "sum"),
            first_visible_day=("Plot_Start", "min"),
            last_visible_day=("Plot_End_Inclusive", "max"),
            nnja_codes=("NNJA_Codes", lambda x: "; ".join(sorted(set(v for v in x if isinstance(v, str) and v)))),
            era5_codes=("ERA5_Codes", lambda x: "; ".join(sorted(set(v for v in x if isinstance(v, str) and v)))),
        )
        .reset_index()
        .sort_values(["overlap_days", "Sensor_Sat"], ascending=[False, True])
    )
    st.dataframe(overlap_summary, use_container_width=True, hide_index=True)

st.subheader("Detailed interval inventory")
display_cols = [
    "Sensor_Sat",
    "Sensor",
    "Satellite",
    "Section",
    "Start_Date",
    "End_Date",
    "Start_Day_Label",
    "End_Day_Label",
    "Selected_Duration_Days",
    "Status",
    "Comparison_Status",
    "NNJA_Codes",
    "ERA5_Codes",
    "ERA_Interim_Only_Codes",
    "NNJA_Source_Labels",
    "ERA_Source_Labels",
]
show_cols = [c for c in display_cols if c in filtered_df.columns]
st.dataframe(
    filtered_df[show_cols].sort_values(["Sensor_Sat", "Start_Date", "Status"]),
    use_container_width=True,
    hide_index=True,
)

csv_bytes = filtered_df[show_cols].to_csv(index=False).encode("utf-8")
st.download_button(
    "Download filtered intervals as CSV",
    data=csv_bytes,
    file_name="nnja_era5_filtered_daily_intervals.csv",
    mime="text/csv",
)
