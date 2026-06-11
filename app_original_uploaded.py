
import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime

# Configure page layout
st.set_page_config(layout="wide", page_title="Satellite DA Timeline")

# Title and Academic Description
st.title("🛰️ Interactive Timeline of Satellite Data Assimilation: NNJA vs. ERA5")
st.markdown("""
**Description:** 
This interactive dashboard provides a comparative visualization of satellite observation usage between the **NOAA-NASA Joint Archive (NNJA)** and the **ECMWF ERA5** reanalysis system. 

It allows researchers to systematically investigate the availability of various satellite radiances and sounding instruments across different eras, highlighting data assimilated by ERA5 versus observations archived exclusively in NNJA but not actively assimilated in the baseline ERA5 configuration.
""")

@st.cache_data
def load_data():
    df = pd.read_csv('nnja_era5_full_inventory_v7.csv')
    # Using 'mixed' format just to be absolutely safe against any variations
    df['Start_Date'] = pd.to_datetime(df['Start_Date'], format='mixed')
    df['End_Date'] = pd.to_datetime(df['End_Date'], format='mixed')
    return df

df = load_data()

# Sidebar: Temporal Filtering
st.sidebar.header("Temporal Filter")
st.sidebar.markdown("Define the temporal window for the observation inventory.")

min_date = datetime(1978, 1, 1)
max_date = datetime(2026, 5, 31)

selected_dates = st.sidebar.slider(
    "Observation Period (Year-Month)",
    min_value=min_date,
    max_value=max_date,
    value=(datetime(1990, 1, 1), datetime(2025, 12, 31)),
    format="YYYY-MM"
)

# Data Filtering based on selected dates
mask = (df['Start_Date'] <= selected_dates[1]) & (df['End_Date'] >= selected_dates[0])
filtered_df = df[mask].copy()

if not filtered_df.empty:
    # Constrain plotting boundaries to the selected slider range
    filtered_df['Plot_Start'] = filtered_df['Start_Date'].clip(lower=selected_dates[0])
    filtered_df['Plot_End'] = filtered_df['End_Date'].clip(upper=selected_dates[1])

    # Standardized color scheme for assimilation status
    color_map = {
        "Both": "#2ca02c",             # Green: Archived in NNJA & Assimilated in ERA5
        "ERA5 Only": "#4275ed",        # Blue: Used in ERA5, not explicitly flagged in NNJA
        "NNJA Only": "#F59E0B"         # Amber: Archived in NNJA, missing/blacklisted in ERA5
    }

    # Generate Gantt Chart using Plotly
    fig = px.timeline(
        filtered_df, 
        x_start="Plot_Start", 
        x_end="Plot_End", 
        y="Sensor_Sat", 
        color="Status",
        color_discrete_map=color_map,
        hover_data=["Start_Date", "End_Date", "Status"]
    )

    fig.update_yaxes(autorange="reversed")
    fig.update_layout(
        height=min(1200, max(500, len(filtered_df) * 20)), # Dynamic height adjustment
        xaxis_title="Observation Timeline",
        yaxis_title="Sensor Platform",
        legend_title="Assimilation Status",
        font=dict(size=12)
    )

    # Display Chart
    st.plotly_chart(fig, use_container_width=True)

    # Display Data Table
    st.subheader("Detailed Observation Inventory")
    display_df = filtered_df[['Sensor', 'Satellite', 'Start_Date', 'End_Date', 'Status']].sort_values(['Start_Date', 'Sensor'])
    st.dataframe(display_df, use_container_width=True)
else:
    st.warning("No satellite observation data available for the selected temporal window.")
