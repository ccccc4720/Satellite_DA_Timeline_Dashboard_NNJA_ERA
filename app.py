from pathlib import Path
from datetime import datetime, date

import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(layout="wide", page_title="NNJA / ERA5 / ERA-Interim DA Timeline")

APP_DIR = Path(__file__).resolve().parent
DATA_CANDIDATES = [
    APP_DIR / "nnja_era5_erainterim_validated_inventory.csv",
    APP_DIR / "nnja_era5_erainterim_validated" / "nnja_era5_erainterim_validated_inventory.csv",
]
XLSX_CANDIDATES = [
    APP_DIR / "nnja_era5_erainterim_validated_comparison.xlsx",
    APP_DIR / "nnja_era5_erainterim_validated" / "nnja_era5_erainterim_validated_comparison.xlsx",
]

DATA_CSV = next((p for p in DATA_CANDIDATES if p.exists()), DATA_CANDIDATES[0])
DATA_XLSX = next((p for p in XLSX_CANDIDATES if p.exists()), XLSX_CANDIDATES[0])

DATA_OPTIONS = [
    "ERA5",
    "ERA-Interim",
    "NNJA",
    "ERA5, ERA-Interim, NNJA",
    "ERA5, NNJA",
    "ERA-Interim, NNJA",
    "only NNJA",
]

COLOR_MAP = {
    "ERA5": "#1d4ed8",
    "ERA-Interim": "#93c5fd",
    "ERA5, ERA-Interim": "#3b82f6",
    "ERA5, ERA-Interim, NNJA": "#166534",
    "ERA5, NNJA": "#22c55e",
    "ERA-Interim, NNJA": "#86efac",
    "only NNJA": "#f59e0b",
}

DISPLAY_COLS = [
    "Sensor_Sat", "Sensor", "Satellite", "Section", "Start_Date", "End_Date",
    "Exact_Category", "Selection_Flags", "Duration_Days", "NNJA_Active",
    "ERA5_Active", "ERA_Interim_Active", "Derived_Replacement_Satellite",
    "Replacement_From", "Extension_Action", "Validation_Basis", "Validation_Source_URLs",
    "NNJA_Segment_IDs", "ERA5_Segment_IDs", "ERA_Interim_Segment_IDs",
]

@st.cache_data(show_spinner="Loading validated NNJA / ERA5 / ERA-Interim inventory...")
def load_data(csv_path: str, mtime: float) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    df["Start_Date"] = pd.to_datetime(df["Start_Date"], format="mixed")
    df["End_Date"] = pd.to_datetime(df["End_Date"], format="mixed")
    for col in ["NNJA_Active", "ERA5_Active", "ERA_Interim_Active", "Beyond_ERA_Source_Edge", "Derived_Replacement_Satellite"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.lower().eq("true")
    dedupe_cols = [
        "Match_Key", "Start_Abs_Day_365", "End_Abs_Day_365", "Exact_Category",
        "NNJA_Segment_IDs", "ERA5_Segment_IDs", "ERA_Interim_Segment_IDs",
        "Extension_Action", "Derived_Replacement_Satellite",
    ]
    dedupe_cols = [c for c in dedupe_cols if c in df.columns]
    return df.drop_duplicates(subset=dedupe_cols).copy()


def option_mask(df: pd.DataFrame, option: str, exact_only: bool) -> pd.Series:
    if exact_only and option not in {"ERA5", "ERA-Interim", "NNJA"}:
        return df["Exact_Category"].astype(str).eq(option)
    if option == "ERA5":
        return df["ERA5_Active"]
    if option == "ERA-Interim":
        return df["ERA_Interim_Active"]
    if option == "NNJA":
        return df["NNJA_Active"]
    return df["Selection_Flags"].astype(str).str.contains(option, regex=False, na=False)


def clip_to_window(df: pd.DataFrame, start_dt: pd.Timestamp, end_dt: pd.Timestamp) -> pd.DataFrame:
    mask = (df["Start_Date"] <= end_dt) & (df["End_Date"] >= start_dt)
    out = df.loc[mask].copy()
    if out.empty:
        return out
    out["Plot_Start"] = out["Start_Date"].where(out["Start_Date"] > start_dt, start_dt)
    out["Plot_End"] = out["End_Date"].where(out["End_Date"] < end_dt, end_dt)
    out["Selected_Window_Days"] = (out["Plot_End"] - out["Plot_Start"]).dt.days + 1
    return out

st.title("🛰️ NNJA / ERA5 / ERA-Interim Data Assimilation Timeline")
st.markdown(
    "This dashboard uses the validated 365-day, no-leap daily inventory derived from the pixel-extracted NNJA and ERA observation figures. "
    "NNJA uses the original pixel-derived bars. ERA5 right-edge bars are extended only after platform/status validation. "
    "ERA-Interim is clipped to **1979-01 through 2019-09**."
)

if not DATA_CSV.exists():
    st.error(f"Cannot find inventory CSV: {DATA_CSV}")
    st.stop()

df = load_data(str(DATA_CSV), DATA_CSV.stat().st_mtime)

st.sidebar.header("Data filter")
selected_option = st.sidebar.selectbox("Dataset / overlap option", DATA_OPTIONS, index=3)
exact_only = st.sidebar.checkbox(
    "Exact category only for overlap options",
    value=False,
    help="Off: ERA5, NNJA also includes ERA5, ERA-Interim, NNJA. On: show only rows whose Exact_Category exactly matches the selected overlap label.",
)
sections = sorted(df["Section"].dropna().unique().tolist())
selected_sections = st.sidebar.multiselect("Sections", sections, default=sections)

st.sidebar.header("Temporal filter")
min_date = date(1978, 1, 1)
max_date = date(2025, 12, 31)
start_date, end_date = st.sidebar.slider(
    "Observation period",
    min_value=min_date,
    max_value=max_date,
    value=(date(2019, 1, 1), date(2025, 12, 31)),
    format="YYYY-MM-DD",
)
start_ts = pd.Timestamp(start_date)
end_ts = pd.Timestamp(end_date)

st.sidebar.header("Display")
show_replacements = st.sidebar.checkbox("Include derived replacement satellites", value=True)
show_validation_cols = st.sidebar.checkbox("Show validation columns in table", value=True)
height_per_row = st.sidebar.slider("Timeline row height", 12, 32, 18)
max_chart_height = st.sidebar.slider("Maximum chart height", 500, 2200, 1400, step=100)

filtered = df.loc[option_mask(df, selected_option, exact_only)].copy()
if selected_sections:
    filtered = filtered[filtered["Section"].isin(selected_sections)]
if not show_replacements and "Derived_Replacement_Satellite" in filtered.columns:
    filtered = filtered[~filtered["Derived_Replacement_Satellite"]]
filtered = clip_to_window(filtered, start_ts, end_ts)

st.subheader("Selection summary")
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Visible intervals", f"{len(filtered):,}")
c2.metric("Unique items", f"{filtered['Match_Key'].nunique() if not filtered.empty else 0:,}")
c3.metric("Selected item-days", f"{int(filtered['Selected_Window_Days'].sum()) if not filtered.empty else 0:,}")
c4.metric("Post-2019 extension intervals", f"{int(filtered['Beyond_ERA_Source_Edge'].sum()) if 'Beyond_ERA_Source_Edge' in filtered else 0:,}")
c5.metric("Derived replacement intervals", f"{int(filtered['Derived_Replacement_Satellite'].sum()) if 'Derived_Replacement_Satellite' in filtered else 0:,}")

st.caption(
    "Color legend: ERA5 / ERA-Interim categories use blue tones; NNJA overlap categories use green tones; only NNJA is orange. "
    "Combination labels have no parentheses."
)

if filtered.empty:
    st.warning("No intervals match the selected dataset option, sections, and time window.")
else:
    filtered = filtered.sort_values(["Section", "Sensor", "Satellite", "Plot_Start", "Exact_Category"])
    chart_df = filtered.copy()
    chart_df["Timeline_Item"] = chart_df["Section"] + " | " + chart_df["Sensor_Sat"]
    fig = px.timeline(
        chart_df,
        x_start="Plot_Start",
        x_end="Plot_End",
        y="Timeline_Item",
        color="Exact_Category",
        color_discrete_map=COLOR_MAP,
        hover_data={
            "Sensor_Sat": True,
            "Start_Date": "|%Y-%m-%d",
            "End_Date": "|%Y-%m-%d",
            "Exact_Category": True,
            "Selection_Flags": True,
            "Extension_Action": True,
            "Replacement_From": True,
            "Timeline_Item": False,
        },
    )
    fig.update_yaxes(autorange="reversed")
    fig.update_layout(
        height=min(max_chart_height, max(500, chart_df["Timeline_Item"].nunique() * height_per_row + 160)),
        xaxis_title="Date on 365-day no-leap calendar",
        yaxis_title="Section | Sensor platform",
        legend_title="Exact category",
        margin=dict(l=10, r=10, t=30, b=10),
    )
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("Detailed interval inventory")
    table_cols = [c for c in DISPLAY_COLS if c in filtered.columns]
    if not show_validation_cols:
        table_cols = [c for c in table_cols if c not in {"Validation_Basis", "Validation_Source_URLs"}]
    display_df = filtered[table_cols].copy()
    st.dataframe(display_df, use_container_width=True, hide_index=True)

    csv_bytes = filtered.drop(columns=[c for c in ["Plot_Start", "Plot_End"] if c in filtered.columns]).to_csv(index=False).encode("utf-8")
    st.download_button(
        "Download filtered intervals as CSV",
        data=csv_bytes,
        file_name="filtered_nnja_era5_erainterim_validated_intervals.csv",
        mime="text/csv",
    )

if DATA_XLSX.exists():
    with open(DATA_XLSX, "rb") as f:
        st.download_button(
            "Download full validated Excel workbook",
            data=f.read(),
            file_name=DATA_XLSX.name,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

with st.expander("Dataset notes"):
    st.markdown(
        """
- Calendar: fixed 365-day years, D001-D365, no leap day.
- ERA-Interim active period: 1979-01-01 through 2019-09-30.
- ERA source grey / blue bars mean ERA5 and ERA-Interim before the ERA-Interim cap; green means ERA5 only; red means ERA-Interim only.
- Post-2019 ERA5 right-edge extensions are capped at satellite retirement, data-service stop, or primary-satellite replacement dates.
- Derived replacement satellites such as GOES 19, Himawari 9, Meteosat 10/12 are marked with `Derived_Replacement_Satellite = True`.
"""
    )
