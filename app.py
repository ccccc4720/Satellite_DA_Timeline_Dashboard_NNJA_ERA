from pathlib import Path
from datetime import datetime, date
from functools import reduce
from operator import or_

import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(layout="wide", page_title="NNJA / ERA5 / ERA-Interim DA Timeline")
APP_DIR = Path(__file__).resolve().parent
DATA_CSV_CANDIDATES = [
    APP_DIR / "nnja_era5_erainterim_extended_inventory.csv",
    APP_DIR / "nnja_era5_erainterim_extended" / "nnja_era5_erainterim_extended_inventory.csv",
]
DATA_XLSX_CANDIDATES = [
    APP_DIR / "nnja_era5_erainterim_extended_comparison.xlsx",
    APP_DIR / "nnja_era5_erainterim_extended" / "nnja_era5_erainterim_extended_comparison.xlsx",
]
DATA_OPTIONS = ["ERA5", "ERA-Interim", "NNJA", "(ERA5, ERA-Interim, NNJA)", "(ERA5, NNJA)", "(ERA-Interim, NNJA)", "only NNJA"]
EXACT_CATEGORY_ORDER = ["ERA5", "ERA-Interim", "(ERA5, ERA-Interim)", "(ERA5, ERA-Interim, NNJA)", "(ERA5, NNJA)", "(ERA-Interim, NNJA)", "only NNJA"]
CATEGORY_COLOR_MAP = {
    "ERA5": "#1D4ED8",
    "ERA-Interim": "#60A5FA",
    "(ERA5, ERA-Interim)": "#3B82F6",
    "(ERA5, ERA-Interim, NNJA)": "#16A34A",
    "(ERA5, NNJA)": "#22C55E",
    "(ERA-Interim, NNJA)": "#86EFAC",
    "only NNJA": "#F59E0B",
}

def option_to_mask(df: pd.DataFrame, option: str) -> pd.Series:
    if option == "ERA5":
        return df["ERA5_Active"]
    if option == "ERA-Interim":
        return df["ERA_Interim_Active"]
    if option == "NNJA":
        return df["NNJA_Active"]
    if option == "(ERA5, ERA-Interim, NNJA)":
        return df["ERA5_Active"] & df["ERA_Interim_Active"] & df["NNJA_Active"]
    if option == "(ERA5, NNJA)":
        return df["ERA5_Active"] & df["NNJA_Active"]
    if option == "(ERA-Interim, NNJA)":
        return df["ERA_Interim_Active"] & df["NNJA_Active"]
    if option == "only NNJA":
        return df["NNJA_Active"] & ~df["ERA5_Active"] & ~df["ERA_Interim_Active"]
    return pd.Series(False, index=df.index)

@st.cache_data(show_spinner=False)
def locate_data_file() -> tuple[str, str, float]:
    for p in DATA_CSV_CANDIDATES:
        if p.exists():
            return str(p), "csv", p.stat().st_mtime
    for p in DATA_XLSX_CANDIDATES:
        if p.exists():
            return str(p), "xlsx", p.stat().st_mtime
    raise FileNotFoundError("Cannot find nnja_era5_erainterim_extended_inventory.csv beside app.py or in nnja_era5_erainterim_extended/.")

@st.cache_data(show_spinner=True)
def load_data(path: str, kind: str, mtime: float) -> pd.DataFrame:
    if kind == "csv":
        df = pd.read_csv(path)
    else:
        df = pd.read_excel(path, sheet_name="Comparison_Segments")
    df["Start_Date"] = pd.to_datetime(df["Start_Date"])
    df["End_Date"] = pd.to_datetime(df["End_Date"])
    for col in ["NNJA_Active", "ERA5_Active", "ERA_Interim_Active", "Beyond_ERA_Source_Edge"]:
        if col not in df.columns:
            df[col] = False
        df[col] = df[col].astype(str).str.lower().isin(["true", "1", "yes"])
    for col, default in {
        "Section": "Unknown", "Sensor": "Unknown", "Satellite": "Unknown", "Sensor_Sat": "Unknown", "Match_Key": "Unknown",
        "Exact_Category": "Unknown", "Dataset_Category": "Unknown", "Selection_Flags": "", "NNJA_Codes": "", "ERA5_Codes": "",
        "ERA_Interim_Codes": "", "ERA_Visible_Colors": "", "NNJA_Source_Labels": "", "ERA_Source_Labels": "",
        "NNJA_Segment_IDs": "", "ERA5_Segment_IDs": "", "ERA_Interim_Segment_IDs": "",
    }.items():
        if col not in df.columns:
            df[col] = default
    dedupe = ["Match_Key", "Start_Abs_Day_365", "End_Abs_Day_365", "Exact_Category", "NNJA_Segment_IDs", "ERA5_Segment_IDs", "ERA_Interim_Segment_IDs"]
    return df.drop_duplicates(subset=[c for c in dedupe if c in df.columns]).copy()

st.title("🛰️ NNJA / ERA5 / ERA-Interim daily DA timeline")
st.markdown(
    "Pixel-derived NNJA and ERA observation timelines are compared on a **365-day no-leap daily grid**. "
    "NNJA keeps its original extracted endpoints through **2025-12-31**. ERA bars that reached the final extracted ERA time boundary are extended to **2025-12-31** under the carry-forward assumption."
)
try:
    data_path, data_kind, data_mtime = locate_data_file()
    df = load_data(data_path, data_kind, data_mtime)
except FileNotFoundError as exc:
    st.error(str(exc)); st.stop()

st.sidebar.header("Temporal filter")
min_date = df["Start_Date"].min().to_pydatetime()
max_date = datetime(2025, 12, 31)
selected_start, selected_end = st.sidebar.slider("Observation period", min_value=min_date, max_value=max_date, value=(min_date, max_date), format="YYYY-MM-DD")

st.sidebar.header("Data option")
st.sidebar.caption("Selected options are unioned and then de-duplicated; every exact interval is plotted once.")
selected_options = st.sidebar.multiselect("Choose data sources / overlaps", DATA_OPTIONS, default=["ERA5", "ERA-Interim", "NNJA"])
if not selected_options:
    st.warning("Please select at least one data option."); st.stop()

st.sidebar.header("Subset filters")
sections = sorted(df["Section"].dropna().unique())
selected_sections = st.sidebar.multiselect("Section", sections, default=sections)
sensors = sorted(df["Sensor"].dropna().unique())
selected_sensors = st.sidebar.multiselect("Sensor", sensors, default=sensors)
show_extension = st.sidebar.checkbox("Include ERA extension-assumption intervals", value=True)
search_text = st.sidebar.text_input("Search item", value="", placeholder="e.g., AMSUA, METOP-B, NOAA 15")

mask = (df["Start_Date"] <= selected_end) & (df["End_Date"] >= selected_start)
mask &= df["Section"].isin(selected_sections) & df["Sensor"].isin(selected_sensors)
mask &= reduce(or_, [option_to_mask(df, opt) for opt in selected_options])
if not show_extension:
    mask &= ~df["Beyond_ERA_Source_Edge"]
if search_text.strip():
    q = search_text.strip().casefold()
    text_mask = pd.Series(False, index=df.index)
    for col in ["Sensor_Sat", "Sensor", "Satellite", "Match_Key", "NNJA_Source_Labels", "ERA_Source_Labels"]:
        text_mask |= df[col].fillna("").astype(str).str.casefold().str.contains(q, regex=False)
    mask &= text_mask

fdf = df[mask].copy()
if fdf.empty:
    st.warning("No observation intervals are available for the selected options and date window."); st.stop()

fdf["Plot_Start"] = fdf["Start_Date"].clip(lower=selected_start)
fdf["Plot_End_Inclusive"] = fdf["End_Date"].clip(upper=selected_end)
fdf["Plot_End"] = fdf["Plot_End_Inclusive"] + pd.Timedelta(days=1)
fdf["Selected_Duration_Days"] = (fdf["Plot_End_Inclusive"] - fdf["Plot_Start"]).dt.days + 1
fdf = fdf[fdf["Selected_Duration_Days"] > 0].copy()
fdf = fdf.drop_duplicates(subset=[c for c in ["Match_Key", "Plot_Start", "Plot_End_Inclusive", "Exact_Category", "NNJA_Segment_IDs", "ERA5_Segment_IDs", "ERA_Interim_Segment_IDs"] if c in fdf.columns])

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Visible intervals", f"{len(fdf):,}")
k2.metric("Unique items", f"{fdf['Match_Key'].nunique():,}")
k3.metric("Selected item-days", f"{int(fdf['Selected_Duration_Days'].sum()):,}")
k4.metric("All-three item-days", f"{int(fdf.loc[fdf['Exact_Category'].eq('(ERA5, ERA-Interim, NNJA)'), 'Selected_Duration_Days'].sum()):,}")
k5.metric("only-NNJA item-days", f"{int(fdf.loc[fdf['Exact_Category'].eq('only NNJA'), 'Selected_Duration_Days'].sum()):,}")

with st.expander("Category day counts in selected interval", expanded=False):
    counts = fdf.groupby("Exact_Category", dropna=False)["Selected_Duration_Days"].sum().reindex([c for c in EXACT_CATEGORY_ORDER if c in set(fdf["Exact_Category"])]).dropna().rename("item_days").reset_index()
    st.dataframe(counts, use_container_width=True, hide_index=True)

plot_df = fdf.sort_values(["Section", "Sensor", "Satellite", "Plot_Start", "Exact_Category"])
y_order = list(dict.fromkeys(plot_df["Sensor_Sat"].tolist()))
fig = px.timeline(
    plot_df, x_start="Plot_Start", x_end="Plot_End", y="Sensor_Sat", color="Exact_Category",
    color_discrete_map=CATEGORY_COLOR_MAP,
    category_orders={"Sensor_Sat": y_order, "Exact_Category": EXACT_CATEGORY_ORDER},
    hover_data={"Section": True, "Sensor": True, "Satellite": True, "Start_Day_Label": True, "End_Day_Label": True, "Selected_Duration_Days": True, "Selection_Flags": True, "NNJA_Codes": True, "ERA5_Codes": True, "ERA_Interim_Codes": True, "ERA_Visible_Colors": True, "Beyond_ERA_Source_Edge": True, "Plot_Start": False, "Plot_End": False},
)
fig.update_yaxes(autorange="reversed")
fig.update_layout(height=min(2200, max(560, 24 * len(y_order) + 180)), xaxis_title="Daily timeline, 365-day no-leap calendar", yaxis_title="Normalized sensor / satellite item", legend_title="Exact non-overlapping category", font=dict(size=12), margin=dict(l=10, r=10, t=40, b=20))
st.plotly_chart(fig, use_container_width=True)

st.subheader("Overlap summary")
summary_df = (fdf.groupby(["Sensor_Sat", "Sensor", "Satellite", "Section", "Exact_Category"], dropna=False)
    .agg(selected_days=("Selected_Duration_Days", "sum"), first_visible_day=("Plot_Start", "min"), last_visible_day=("Plot_End_Inclusive", "max"), nnja_codes=("NNJA_Codes", lambda x: "; ".join(sorted(set(v for v in x if isinstance(v, str) and v)))), era5_codes=("ERA5_Codes", lambda x: "; ".join(sorted(set(v for v in x if isinstance(v, str) and v)))), erainterim_codes=("ERA_Interim_Codes", lambda x: "; ".join(sorted(set(v for v in x if isinstance(v, str) and v))))).reset_index().sort_values(["selected_days", "Sensor_Sat"], ascending=[False, True]))
st.dataframe(summary_df, use_container_width=True, hide_index=True)

st.subheader("Detailed interval inventory")
show_cols = [c for c in ["Comparison_Segment_ID", "Sensor_Sat", "Sensor", "Satellite", "Section", "Start_Date", "End_Date", "Start_Day_Label", "End_Day_Label", "Selected_Duration_Days", "Exact_Category", "Selection_Flags", "NNJA_Active", "ERA5_Active", "ERA_Interim_Active", "Beyond_ERA_Source_Edge", "NNJA_Codes", "ERA5_Codes", "ERA_Interim_Codes", "NNJA_Source_Labels", "ERA_Source_Labels"] if c in fdf.columns]
st.dataframe(fdf[show_cols].sort_values(["Sensor_Sat", "Start_Date", "Exact_Category"]), use_container_width=True, hide_index=True)
st.download_button("Download filtered intervals as CSV", data=fdf[show_cols].to_csv(index=False).encode("utf-8"), file_name="nnja_era5_erainterim_filtered_intervals.csv", mime="text/csv")
st.caption(f"Data file: {Path(data_path).name}")
