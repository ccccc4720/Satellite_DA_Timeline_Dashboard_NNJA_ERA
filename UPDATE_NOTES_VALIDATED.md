# NNJA / ERA5 / ERA-Interim validated extension update

This package extends the comparison window to 2025-12-31 on a 365-day no-leap calendar.

Key changes:

- ERA-Interim is hard-capped to 1979-01-01 through 2019-09-30.
- Labels use no parentheses: ERA5, ERA-Interim, NNJA; ERA5, NNJA; ERA-Interim, NNJA; only NNJA.
- NNJA uses the original pixel-derived records.
- ERA post-2019 extensions are not blindly extended. Each right-edge ERA source segment is validated with five checks and is capped or replaced if a satellite was retired, data service stopped, or a primary satellite changed.
- Full daily tables are available as CSV; the Excel workbook contains the comparison, validation, summary, and input/provenance sheets.

GitHub / Streamlit minimum deployment files:

- app.py
- requirements.txt
- nnja_era5_erainterim_validated_inventory.csv
- nnja_era5_erainterim_validated_comparison.xlsx

The app can also read the inventory and workbook from the folder:

- nnja_era5_erainterim_validated/
