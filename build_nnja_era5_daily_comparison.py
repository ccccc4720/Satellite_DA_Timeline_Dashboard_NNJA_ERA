#!/usr/bin/env python3
"""Build a day-level NNJA vs ERA5-DA comparison inventory from pixel-derived segments.

Inputs:
  - full_nnja_daily/all_line_segments_daily_units.csv
  - era_da_daily_erainterim/era_da_observation_inventory_segments_daily_units.csv

Definitions:
  - NNJA active: any NNJA pixel-derived segment, including one-day black markers.
  - ERA5 DA active: ERA colors grey, green, blue.
  - ERA-Interim-only: ERA color red (kept as a flag/status, not counted as ERA5 DA).
  - Calendar: fixed 365-day years, D001..D365; no leap day.
"""
import csv
import json
import math
import os
import re
import zipfile
from collections import defaultdict, Counter
from datetime import date

BASE_YEAR = 1978
END_YEAR_EXCLUSIVE = 2020
END_YEAR = END_YEAR_EXCLUSIVE - 1
DAYS_PER_YEAR = 365
COMPARISON_START_DAY = 1
COMPARISON_END_DAY = (END_YEAR_EXCLUSIVE - BASE_YEAR) * DAYS_PER_YEAR

MONTH_LENGTHS_365 = [31,28,31,30,31,30,31,31,30,31,30,31]
MONTH_NAMES = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]

def yday_to_month_day(day_of_year):
    day = int(day_of_year)
    if day < 1:
        day = 1
    if day > 365:
        day = 365
    m = 1
    for ml in MONTH_LENGTHS_365:
        if day <= ml:
            return m, day
        day -= ml
        m += 1
    return 12, 31

def day365_label(global_day):
    g = int(global_day)
    year = BASE_YEAR + (g - 1) // DAYS_PER_YEAR
    doy = ((g - 1) % DAYS_PER_YEAR) + 1
    return f"{year}-D{doy:03d}"

def date365_string(global_day):
    g = int(global_day)
    year = BASE_YEAR + (g - 1) // DAYS_PER_YEAR
    doy = ((g - 1) % DAYS_PER_YEAR) + 1
    month, day = yday_to_month_day(doy)
    return f"{year:04d}-{month:02d}-{day:02d}"

def split_label(global_day):
    g = int(global_day)
    year = BASE_YEAR + (g - 1) // DAYS_PER_YEAR
    doy = ((g - 1) % DAYS_PER_YEAR) + 1
    return year, doy, f"{year}-D{doy:03d}", date365_string(g)

def absday_from_year_doy(year, doy):
    return (int(year) - BASE_YEAR) * DAYS_PER_YEAR + int(doy)

def clean(s):
    s = (s or '').upper().strip()
    s = s.replace('–','-').replace('—','-').replace('_',' ')
    s = re.sub(r'\s+', ' ', s)
    return s

def norm_sensor(s):
    s = clean(s)
    replacements = {
        'AMSR 2':'AMSR-2', 'AMSR2':'AMSR-2',
        'AMSR E':'AMSRE', 'AMSR-E':'AMSRE',
        'AMSU A':'AMSUA', 'AMSU-A':'AMSUA',
        'AMSU B':'AMSUB', 'AMSU-B':'AMSUB',
        'TRMM':'TMI',
    }
    for a,b in replacements.items():
        s = s.replace(a,b)
    aliases = {
        'AIRS':'AIRS', 'AMSR-2':'AMSR-2', 'AMSRE':'AMSRE', 'AMSUA':'AMSUA', 'AMSUB':'AMSUB',
        'ATMS':'ATMS', 'AVHRR':'AVHRR', 'CRIS':'CRIS', 'GMI':'GMI', 'HIRS':'HIRS', 'IASI':'IASI',
        'MHS':'MHS', 'MSU':'MSU', 'SAPHIR':'SAPHIR', 'SEVIRI':'SEVIRI', 'SSMI':'SSMI', 'SSMIS':'SSMIS',
        'SSU':'SSU', 'TMI':'TMI', 'GEOS':'GEOS', 'IMAGER':'IMAGER', 'ABI':'ABI', 'AHI':'AHI',
        'MWHS2':'MWHS2', 'MWHS':'MWHS'
    }
    return aliases.get(s, s)

def norm_sat(s):
    s = clean(s)
    s = s.replace('GPM-CORE','GPM').replace('GPM CORE','GPM')
    s = s.replace('DMSP-', 'DMSP ')
    s = s.replace('NOAA-', 'NOAA ')
    s = s.replace('TIROS N', 'TIROS-N')
    s = s.replace('MEGHA TROPIQUES', 'MEGHA-TROPIQUES')
    if re.match(r'^METOP [ABC]$', s):
        s = s.replace('METOP ', 'METOP-')
    s = re.sub(r'NOAA\s*0+(\d+)', r'NOAA \1', s)
    s = re.sub(r'DMSP\s*0*(\d+)', r'DMSP \1', s)
    s = re.sub(r'GOES\s*0*(\d+)', r'GOES \1', s)
    s = re.sub(r'METEOSAT\s*0*(\d+)', r'METEOSAT \1', s)
    aliases = {
        'GPM-CORE':'GPM', 'GPM CORE':'GPM', 'GPM':'GPM',
        'NPP':'NPP', 'SNPP':'NPP', 'S-NPP':'NPP',
        'TIROS-N':'TIROS-N',
        'MEGHA-TROPIQUES':'MEGHA-TROPIQUES',
    }
    return aliases.get(s, s)

def parse_nnja_label(row_label, source_path=''):
    label = (row_label or '').strip()
    if not label:
        return '', ''
    parts = label.split(' ', 1)
    if len(parts) == 1:
        sensor = parts[0]
        sat = ''
    else:
        sensor, sat = parts
    # Special: NNJA row label 'trmm TRMM' has source_path ending in tmi and matches ERA TMI.
    if sensor.lower() == 'trmm' or '/tmi' in (source_path or '').lower():
        sensor = 'TMI'
    return norm_sensor(sensor), norm_sat(sat)

def parse_era_label(row_label):
    u = clean(row_label).replace('⚓', '').strip()
    # Suffix removal while preserving core satellite/sensor tokens.
    u = re.sub(r'\bRAD\.?\b', ' ', u)
    u = re.sub(r'\bALL[- ]?SKY\b', ' ', u)
    u = re.sub(r'\bCM SAF\b', ' ', u)
    u = re.sub(r'\bTOVS1B\b', ' ', u)
    u = re.sub(r'\s+', ' ', u).strip()

    m = re.match(r'^(GOES)\s+(\d+)\s+GEOS', u)
    if m:
        return 'GEOS', norm_sat(f'GOES {m.group(2)}')
    m = re.match(r'^(METEOSAT)\s+(\d+)\s+GEOS', u)
    if m:
        sat = norm_sat(f'METEOSAT {m.group(2)}')
        # NNJA figure identifies Meteosat 8-11 as SEVIRI; ERA plot uses generic GEOS Radiance wording.
        if int(m.group(2)) in (8, 9, 10, 11):
            return 'SEVIRI', sat
        return 'GEOS', sat
    m = re.match(r'^(HIMAWARI)\s+(\d+)\s+GEOS', u)
    if m:
        return 'AHI', norm_sat(f'HIMAWARI {m.group(2)}')
    m = re.match(r'^(MTSAT-?\dR?|MTSAT-?\d)\s+GEOS', u)
    if m:
        return 'IMAGER', norm_sat(m.group(1).replace('MTSAT ', 'MTSAT-'))
    if u.startswith('SAPHIR'):
        return 'SAPHIR', 'MEGHA-TROPIQUES'
    if u.startswith('TRMM TMI'):
        return 'TMI', 'TRMM'
    m = re.match(r'^(GCOM-W1)\s+(AMSR-?2)', u)
    if m:
        return 'AMSR-2', norm_sat(m.group(1))
    m = re.match(r'^(GPM)\s+(GMI)', u)
    if m:
        return 'GMI', 'GPM'
    # Rows such as 'MHS METOP-C MHS'.
    m = re.match(r'^MHS\s+(.+?)\s+MHS', u)
    if m:
        return 'MHS', norm_sat(m.group(1))
    # Rows with satellite then sensor: 'NOAA 17 AMSUB', 'METOP-B IASI', 'AQUA AIRS'.
    m = re.match(r'^(NOAA[- ]?\d+|METOP-?[ABC]|NPP|AQUA|TIROS-N|DMSP\s*\d+)\s+(.+)$', u)
    if m:
        sat = norm_sat(m.group(1))
        rest = m.group(2).strip()
        for tok in ['AMSR-2','AMSR2','AMSRE','AMSU-A','AMSUA','AMSUB','ATMS','CRIS','IASI','AIRS','SSMIS','SSMI','SSU','HIRS','MSU','MHS','GMI']:
            if re.search(r'\b' + re.escape(tok) + r'\b', rest):
                return norm_sensor(tok), sat
    m = re.match(r'^(FY-3C)\s+(MWHS2)', u)
    if m:
        return 'MWHS2', norm_sat(m.group(1))
    m = re.match(r'^(FY-3B)\s+(MWHS)', u)
    if m:
        return 'MWHS', norm_sat(m.group(1))
    return 'UNKNOWN', norm_sat(u)

def canonical_item(sensor, satellite):
    return f"{sensor} ({satellite})" if satellite else sensor

def status_from_flags(has_nnja, has_era5, has_erai):
    if has_nnja and has_era5 and has_erai:
        return 'Both + ERA-Interim-only marker'
    if has_nnja and has_era5:
        return 'Both'
    if has_nnja and (not has_era5) and has_erai:
        return 'NNJA + ERA-Interim-only (not ERA5)'
    if has_nnja:
        return 'NNJA Only'
    if has_era5:
        return 'ERA5 Only'
    if has_erai:
        return 'ERA-Interim Only (not ERA5)'
    return ''

def comparison_status(status):
    if status in ('Both', 'Both + ERA-Interim-only marker'):
        return 'Both'
    if status.startswith('NNJA'):
        return 'NNJA Only'
    if status.startswith('ERA5'):
        return 'ERA5 Only'
    if status.startswith('ERA-Interim'):
        return 'ERA-Interim Only'
    return status

def era5_flag_for_color(color):
    return color in {'grey', 'green', 'blue'}

def inclusive_interval_from_row(row):
    return absday_from_year_doy(row['start_year'], row['start_day_of_year']), absday_from_year_doy(row['end_year'], row['end_day_of_year'])

def add_day_range(daymap, key, start, end, payload):
    start = max(COMPARISON_START_DAY, int(start))
    end = min(COMPARISON_END_DAY, int(end))
    if end < start:
        return 0
    for day in range(start, end + 1):
        daymap[key][day].append(payload)
    return end - start + 1

def sorted_join(items):
    vals = sorted(str(x) for x in set(items) if str(x) != '')
    return '; '.join(vals)

def compact_segment_ids(payloads):
    return sorted_join(p.get('segment_id','') for p in payloads)

def infer_section(sensor):
    if sensor in {'GEOS', 'SEVIRI', 'AHI', 'IMAGER', 'ABI'}:
        return 'Geostationary radiances'
    if sensor in {'AIRS', 'IASI', 'CRIS'}:
        return 'Hyperspectral infrared'
    if sensor in {'HIRS', 'SSU', 'AVHRR'}:
        return 'Multispectral infrared'
    if sensor in {'GMI','AMSR-2','AMSRE','TMI','SSMI','SSMIS'}:
        return 'Microwave imagers'
    if sensor in {'SAPHIR','MWHS2','MWHS','MHS','ATMS','MSU','AMSUA','AMSUB'}:
        return 'Microwave sounders'
    return 'Other'

def build_comparison(nnja_path, era_path, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    nnja_days = defaultdict(lambda: defaultdict(list))
    era5_days = defaultdict(lambda: defaultdict(list))
    erai_days = defaultdict(lambda: defaultdict(list))
    key_meta = {}
    mapping_rows = []
    nnja_input_rows = []
    era_input_rows = []

    # Read NNJA segments.
    with open(nnja_path, newline='', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            sensor, sat = parse_nnja_label(row['row_label'], row.get('source_path',''))
            key = f'{sensor}|{sat}'
            item = canonical_item(sensor, sat)
            key_meta.setdefault(key, {'Sensor': sensor, 'Satellite': sat, 'Sensor_Sat': item, 'Section': infer_section(sensor), 'NNJA_Source_Labels': set(), 'ERA_Source_Labels': set()})
            key_meta[key]['NNJA_Source_Labels'].add(row['row_label'])
            start, end = inclusive_interval_from_row(row)
            clipped_days = max(0, min(end, COMPARISON_END_DAY) - max(start, COMPARISON_START_DAY) + 1)
            payload = {
                'source':'NNJA',
                'segment_id': row['segment_id'],
                'row_index': row['row_index'],
                'row_label': row['row_label'],
                'source_path': row.get('source_path',''),
                'code': row.get('code',''),
                'color': row.get('color',''),
                'thickness': row.get('thickness',''),
                'source_kind': row.get('source_kind',''),
                'x_start_px': row.get('x_start_px',''),
                'x_end_px': row.get('x_end_px',''),
            }
            add_day_range(nnja_days, key, start, end, payload)
            row2 = dict(row)
            row2.update({'normalized_sensor':sensor, 'normalized_satellite':sat, 'match_key':key, 'comparison_start_abs_day':start, 'comparison_end_abs_day':end, 'comparison_clipped_days':clipped_days})
            nnja_input_rows.append(row2)

    # Read ERA segments.
    with open(era_path, newline='', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            sensor, sat = parse_era_label(row['row_label'])
            key = f'{sensor}|{sat}'
            item = canonical_item(sensor, sat)
            key_meta.setdefault(key, {'Sensor': sensor, 'Satellite': sat, 'Sensor_Sat': item, 'Section': row.get('section') or infer_section(sensor), 'NNJA_Source_Labels': set(), 'ERA_Source_Labels': set()})
            # Prefer actual ERA section for keys that only exist in ERA.
            if row.get('section'):
                key_meta[key]['Section'] = row.get('section')
            key_meta[key]['ERA_Source_Labels'].add(row['row_label'])
            start, end = inclusive_interval_from_row(row)
            payload = {
                'source':'ERA',
                'segment_id': row['segment_id'],
                'row_index': row['row_index'],
                'row_label': row['row_label'],
                'section': row.get('section',''),
                'code': row.get('code',''),
                'color': row.get('color',''),
                'thickness': row.get('thickness',''),
                'legend_description': row.get('legend_description',''),
                'source_kind': row.get('source_kind',''),
                'pixel_x_start': row.get('pixel_x_start',''),
                'pixel_x_end_exclusive': row.get('pixel_x_end_exclusive',''),
                'pixel_width': row.get('pixel_width',''),
            }
            target = era5_days if era5_flag_for_color(row.get('color','')) else erai_days
            add_day_range(target, key, start, end, payload)
            clipped_days = max(0, min(end, COMPARISON_END_DAY) - max(start, COMPARISON_START_DAY) + 1)
            row2 = dict(row)
            row2.update({'normalized_sensor':sensor, 'normalized_satellite':sat, 'match_key':key, 'comparison_start_abs_day':start, 'comparison_end_abs_day':end, 'comparison_clipped_days':clipped_days, 'era5_da_active_color': era5_flag_for_color(row.get('color',''))})
            era_input_rows.append(row2)

    keys = sorted(key_meta.keys(), key=lambda k: (key_meta[k]['Section'], key_meta[k]['Sensor'], key_meta[k]['Satellite']))
    comparison_rows = []
    daily_long_rows = []
    # Only statuses: include active days in any source.
    for key in keys:
        meta = key_meta[key]
        active_days = sorted(set(nnja_days.get(key, {}).keys()) | set(era5_days.get(key, {}).keys()) | set(erai_days.get(key, {}).keys()))
        if not active_days:
            continue
        current_state = None
        run_start = None
        run_payload = None

        def make_state(day):
            n_payloads = nnja_days.get(key, {}).get(day, [])
            e5_payloads = era5_days.get(key, {}).get(day, [])
            erai_payloads = erai_days.get(key, {}).get(day, [])
            has_nnja = bool(n_payloads)
            has_era5 = bool(e5_payloads)
            has_erai = bool(erai_payloads)
            stat = status_from_flags(has_nnja, has_era5, has_erai)
            if not stat:
                return None
            n_codes = tuple(sorted(set(p['code'] for p in n_payloads if p.get('code'))))
            e5_codes = tuple(sorted(set(p['code'] for p in e5_payloads if p.get('code'))))
            erai_codes = tuple(sorted(set(p['code'] for p in erai_payloads if p.get('code'))))
            n_src_kinds = tuple(sorted(set(p['source_kind'] for p in n_payloads if p.get('source_kind'))))
            era_colors = tuple(sorted(set(p['color'] for p in e5_payloads + erai_payloads if p.get('color'))))
            # State includes source codes/kinds so short pixel endpoints remain split.
            state = (stat, n_codes, e5_codes, erai_codes, n_src_kinds, era_colors)
            payload = {
                'nnja_payloads': n_payloads,
                'era5_payloads': e5_payloads,
                'erai_payloads': erai_payloads,
                'has_nnja': has_nnja,
                'has_era5': has_era5,
                'has_erai': has_erai,
                'status': stat,
                'comparison_status': comparison_status(stat),
                'nnja_codes': '; '.join(n_codes),
                'era5_codes': '; '.join(e5_codes),
                'erainterim_only_codes': '; '.join(erai_codes),
                'source_kinds': '; '.join(n_src_kinds),
                'era_visible_colors': '; '.join(era_colors),
            }
            return state, payload

        prev_day = None
        for day in active_days:
            state_payload = make_state(day)
            if state_payload is None:
                continue
            state, payload = state_payload
            if current_state is None:
                current_state = state; run_start = day; run_payload = payload
            elif day != prev_day + 1 or state != current_state:
                # close previous run
                start_year, start_doy, start_label, start_date = split_label(run_start)
                end_year, end_doy, end_label, end_date = split_label(prev_day)
                comparison_rows.append({
                    'Sensor_Sat': meta['Sensor_Sat'],
                    'Sensor': meta['Sensor'],
                    'Satellite': meta['Satellite'],
                    'Section': meta['Section'],
                    'Match_Key': key,
                    'Start_Date': start_date,
                    'End_Date': end_date,
                    'Start_Day_Label': start_label,
                    'End_Day_Label': end_label,
                    'Start_Abs_Day_365': run_start,
                    'End_Abs_Day_365': prev_day,
                    'Duration_Days': prev_day - run_start + 1,
                    'Status': run_payload['status'],
                    'Comparison_Status': run_payload['comparison_status'],
                    'NNJA_Active': run_payload['has_nnja'],
                    'ERA5_DA_Active': run_payload['has_era5'],
                    'ERA_Interim_Only_Active': run_payload['has_erai'],
                    'NNJA_Codes': run_payload['nnja_codes'],
                    'ERA5_Codes': run_payload['era5_codes'],
                    'ERA_Interim_Only_Codes': run_payload['erainterim_only_codes'],
                    'ERA_Visible_Colors': run_payload['era_visible_colors'],
                    'NNJA_Source_Kinds': run_payload['source_kinds'],
                    'NNJA_Segment_IDs': compact_segment_ids(run_payload['nnja_payloads']),
                    'ERA5_Segment_IDs': compact_segment_ids(run_payload['era5_payloads']),
                    'ERA_Interim_Only_Segment_IDs': compact_segment_ids(run_payload['erai_payloads']),
                    'NNJA_Source_Labels': sorted_join(meta['NNJA_Source_Labels']),
                    'ERA_Source_Labels': sorted_join(meta['ERA_Source_Labels']),
                    'Calendar': '365_day_no_leap',
                    'Precision_Note': 'day bins from pixel-derived endpoints; no leap day; ERA figure coverage clipped to 1978-D001..2019-D365'
                })
                current_state = state; run_start = day; run_payload = payload
            prev_day = day
        if current_state is not None:
            start_year, start_doy, start_label, start_date = split_label(run_start)
            end_year, end_doy, end_label, end_date = split_label(prev_day)
            comparison_rows.append({
                'Sensor_Sat': meta['Sensor_Sat'],
                'Sensor': meta['Sensor'],
                'Satellite': meta['Satellite'],
                'Section': meta['Section'],
                'Match_Key': key,
                'Start_Date': start_date,
                'End_Date': end_date,
                'Start_Day_Label': start_label,
                'End_Day_Label': end_label,
                'Start_Abs_Day_365': run_start,
                'End_Abs_Day_365': prev_day,
                'Duration_Days': prev_day - run_start + 1,
                'Status': run_payload['status'],
                'Comparison_Status': run_payload['comparison_status'],
                'NNJA_Active': run_payload['has_nnja'],
                'ERA5_DA_Active': run_payload['has_era5'],
                'ERA_Interim_Only_Active': run_payload['has_erai'],
                'NNJA_Codes': run_payload['nnja_codes'],
                'ERA5_Codes': run_payload['era5_codes'],
                'ERA_Interim_Only_Codes': run_payload['erainterim_only_codes'],
                'ERA_Visible_Colors': run_payload['era_visible_colors'],
                'NNJA_Source_Kinds': run_payload['source_kinds'],
                'NNJA_Segment_IDs': compact_segment_ids(run_payload['nnja_payloads']),
                'ERA5_Segment_IDs': compact_segment_ids(run_payload['era5_payloads']),
                'ERA_Interim_Only_Segment_IDs': compact_segment_ids(run_payload['erai_payloads']),
                'NNJA_Source_Labels': sorted_join(meta['NNJA_Source_Labels']),
                'ERA_Source_Labels': sorted_join(meta['ERA_Source_Labels']),
                'Calendar': '365_day_no_leap',
                'Precision_Note': 'day bins from pixel-derived endpoints; no leap day; ERA figure coverage clipped to 1978-D001..2019-D365'
            })

    # De-duplicate rows exactly in case multiple parsed rows collapse to identical intervals.
    deduped = []
    seen = set()
    dedupe_cols = ['Match_Key','Start_Abs_Day_365','End_Abs_Day_365','Status','NNJA_Codes','ERA5_Codes','ERA_Interim_Only_Codes']
    for r in comparison_rows:
        tup = tuple(r[c] for c in dedupe_cols)
        if tup in seen:
            continue
        seen.add(tup)
        deduped.append(r)
    comparison_rows = sorted(deduped, key=lambda r: (r['Section'], r['Sensor'], r['Satellite'], int(r['Start_Abs_Day_365']), r['Status']))
    for i, r in enumerate(comparison_rows, start=1):
        r['Comparison_Segment_ID'] = i

    # Generate per-key matrix with statuses by day-of-year. This is compact enough (keys * years * 365).
    matrix_rows = []
    by_key_year_day = defaultdict(lambda: defaultdict(dict))
    for r in comparison_rows:
        key = r['Match_Key']
        start = int(r['Start_Abs_Day_365']); end = int(r['End_Abs_Day_365'])
        for day in range(start, end + 1):
            year, doy, _, _ = split_label(day)
            cell = r['Comparison_Status']
            # Add ERAI flag only where it matters.
            if r['ERA_Interim_Only_Active'] == True or str(r['ERA_Interim_Only_Active']).lower() == 'true':
                if cell == 'NNJA Only':
                    cell = 'NNJA Only + ERAI-only'
                elif cell == 'Both':
                    cell = 'Both + ERAI-only'
                elif cell == 'ERA-Interim Only':
                    cell = 'ERAI-only'
            by_key_year_day[key][year][doy] = cell
    for key in sorted(by_key_year_day.keys(), key=lambda k: (key_meta[k]['Section'], key_meta[k]['Sensor'], key_meta[k]['Satellite'])):
        meta = key_meta[key]
        for yr in range(BASE_YEAR, END_YEAR_EXCLUSIVE):
            values = by_key_year_day[key].get(yr, {})
            if not values:
                continue
            row = {'Sensor_Sat': meta['Sensor_Sat'], 'Sensor': meta['Sensor'], 'Satellite': meta['Satellite'], 'Section': meta['Section'], 'Match_Key': key, 'Year': yr}
            for d in range(1, 366):
                row[f'D{d:03d}'] = values.get(d, '')
            matrix_rows.append(row)

    # Daily long status summary, but keep to active days only.
    daily_long_rows = []
    for r in comparison_rows:
        for day in range(int(r['Start_Abs_Day_365']), int(r['End_Abs_Day_365']) + 1):
            yr, doy, lbl, ds = split_label(day)
            daily_long_rows.append({
                'Sensor_Sat': r['Sensor_Sat'], 'Sensor': r['Sensor'], 'Satellite': r['Satellite'], 'Section': r['Section'], 'Match_Key': r['Match_Key'],
                'Date_365': ds, 'Day_Label': lbl, 'Abs_Day_365': day, 'Year': yr, 'Day_Of_Year': doy,
                'Status': r['Status'], 'Comparison_Status': r['Comparison_Status'], 'NNJA_Active': r['NNJA_Active'], 'ERA5_DA_Active': r['ERA5_DA_Active'], 'ERA_Interim_Only_Active': r['ERA_Interim_Only_Active'],
                'Comparison_Segment_ID': r['Comparison_Segment_ID']
            })

    # Matching rows: key-level provenance.
    key_summary_rows = []
    for key in sorted(key_meta.keys(), key=lambda k: (key_meta[k]['Section'], key_meta[k]['Sensor'], key_meta[k]['Satellite'])):
        meta = key_meta[key]
        comp_rows = [r for r in comparison_rows if r['Match_Key'] == key]
        if not comp_rows:
            continue
        counts = Counter()
        for r in comp_rows:
            counts[r['Comparison_Status']] += int(r['Duration_Days'])
        key_summary_rows.append({
            'Match_Key': key,
            'Sensor_Sat': meta['Sensor_Sat'],
            'Sensor': meta['Sensor'],
            'Satellite': meta['Satellite'],
            'Section': meta['Section'],
            'NNJA_Source_Labels': sorted_join(meta['NNJA_Source_Labels']),
            'ERA_Source_Labels': sorted_join(meta['ERA_Source_Labels']),
            'Both_Days': counts['Both'],
            'NNJA_Only_Days': counts['NNJA Only'],
            'ERA5_Only_Days': counts['ERA5 Only'],
            'ERA_Interim_Only_Days': counts['ERA-Interim Only'],
            'Total_Active_Days': sum(counts.values()),
        })

    # Summary rows.
    summary = {
        'base_year': BASE_YEAR,
        'end_year_exclusive': END_YEAR_EXCLUSIVE,
        'comparison_window': f'{BASE_YEAR}-D001..{END_YEAR}-D365',
        'nnja_input_segments': len(nnja_input_rows),
        'era_input_segments': len(era_input_rows),
        'unique_match_keys': len(key_summary_rows),
        'comparison_segments': len(comparison_rows),
        'daily_long_active_rows': len(daily_long_rows),
        'matrix_rows': len(matrix_rows),
        'status_day_counts': Counter(),
        'detailed_status_day_counts': Counter(),
    }
    for r in comparison_rows:
        summary['status_day_counts'][r['Comparison_Status']] += int(r['Duration_Days'])
        summary['detailed_status_day_counts'][r['Status']] += int(r['Duration_Days'])
    # Convert Counters to normal dicts for JSON.
    summary['status_day_counts'] = dict(summary['status_day_counts'])
    summary['detailed_status_day_counts'] = dict(summary['detailed_status_day_counts'])

    def write_csv(path, rows, fieldnames=None):
        if fieldnames is None:
            if rows:
                fieldnames = list(rows[0].keys())
            else:
                fieldnames = []
        with open(path, 'w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
            w.writeheader()
            for row in rows:
                w.writerow(row)

    comparison_fields = [
        'Comparison_Segment_ID','Sensor_Sat','Sensor','Satellite','Section','Match_Key',
        'Start_Date','End_Date','Start_Day_Label','End_Day_Label','Start_Abs_Day_365','End_Abs_Day_365','Duration_Days',
        'Status','Comparison_Status','NNJA_Active','ERA5_DA_Active','ERA_Interim_Only_Active',
        'NNJA_Codes','ERA5_Codes','ERA_Interim_Only_Codes','ERA_Visible_Colors','NNJA_Source_Kinds',
        'NNJA_Segment_IDs','ERA5_Segment_IDs','ERA_Interim_Only_Segment_IDs','NNJA_Source_Labels','ERA_Source_Labels','Calendar','Precision_Note'
    ]
    key_summary_fields = ['Match_Key','Sensor_Sat','Sensor','Satellite','Section','NNJA_Source_Labels','ERA_Source_Labels','Both_Days','NNJA_Only_Days','ERA5_Only_Days','ERA_Interim_Only_Days','Total_Active_Days']
    matrix_fields = ['Sensor_Sat','Sensor','Satellite','Section','Match_Key','Year'] + [f'D{d:03d}' for d in range(1,366)]
    daily_fields = ['Sensor_Sat','Sensor','Satellite','Section','Match_Key','Date_365','Day_Label','Abs_Day_365','Year','Day_Of_Year','Status','Comparison_Status','NNJA_Active','ERA5_DA_Active','ERA_Interim_Only_Active','Comparison_Segment_ID']

    comparison_csv = os.path.join(out_dir, 'nnja_era5_daily_comparison_inventory.csv')
    write_csv(comparison_csv, comparison_rows, comparison_fields)
    write_csv(os.path.join(out_dir, 'nnja_era5_daily_key_summary.csv'), key_summary_rows, key_summary_fields)
    write_csv(os.path.join(out_dir, 'nnja_era5_daily_365_matrix.csv'), matrix_rows, matrix_fields)
    write_csv(os.path.join(out_dir, 'nnja_era5_daily_long.csv'), daily_long_rows, daily_fields)
    write_csv(os.path.join(out_dir, 'nnja_input_segments_normalized.csv'), nnja_input_rows)
    write_csv(os.path.join(out_dir, 'era_input_segments_normalized.csv'), era_input_rows)
    with open(os.path.join(out_dir, 'nnja_era5_daily_comparison_summary.json'), 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    return summary, comparison_rows, key_summary_rows, matrix_rows, daily_long_rows

if __name__ == '__main__':
    out = '/mnt/data/nnja_era5_daily_comparison'
    summary, *_ = build_comparison(
        '/mnt/data/full_nnja_daily/all_line_segments_daily_units.csv',
        '/mnt/data/era_da_daily_erainterim/era_da_observation_inventory_segments_daily_units.csv',
        out,
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
