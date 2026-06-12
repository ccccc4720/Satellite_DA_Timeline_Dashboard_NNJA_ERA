#!/usr/bin/env python3
import csv
import json
from pathlib import Path
from artifact_tool import Workbook, SpreadsheetFile

BASE = Path('/mnt/data/nnja_era5_erainterim_validated')
OUT = BASE / 'nnja_era5_erainterim_validated_comparison.xlsx'

HEADER_FMT = {
    'fill': '#1F4E78',
    'font': {'bold': True, 'color': '#FFFFFF'},
    'horizontal_alignment': 'center',
    'vertical_alignment': 'center',
    'wrap_text': True,
}
TITLE_FMT = {
    'fill': '#0F172A',
    'font': {'bold': True, 'color': '#FFFFFF', 'size': 14},
    'horizontal_alignment': 'left',
    'vertical_alignment': 'center',
}
LABEL_FMT = {'font': {'bold': True}, 'fill': '#E2E8F0', 'wrap_text': True}


def read_csv(path, limit=None):
    with open(path, newline='', encoding='utf-8') as f:
        reader = csv.reader(f)
        rows = []
        for i, row in enumerate(reader):
            rows.append(row)
            if limit is not None and i + 1 >= limit:
                break
    return rows


def write_rows(sheet, rows):
    if not rows:
        return 0, 0
    ncols = max(len(r) for r in rows)
    values = [r + [''] * (ncols - len(r)) for r in rows]
    sheet.get_range_by_indexes(0, 0, len(values), ncols).values = values
    return len(values), ncols


def col_name(n):
    s = ''
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def table_name(name):
    return ''.join(ch if ch.isalnum() else '_' for ch in name)[:180] + '_tbl'


def add_csv_sheet(wb, sheet_name, filename, max_rows=None, make_table=True):
    sheet = wb.worksheets.add(sheet_name)
    rows = read_csv(BASE / filename, limit=max_rows)
    nrows, ncols = write_rows(sheet, rows)
    if nrows and ncols:
        sheet.get_range_by_indexes(0, 0, 1, ncols).format = HEADER_FMT
        sheet.freeze_panes.freeze_rows(1)
        if make_table and nrows > 1:
            try:
                sheet.tables.add(f"A1:{col_name(ncols)}{nrows}", True, table_name(sheet_name))
            except Exception:
                pass
        # Readable widths without expensive autofit.
        for c in range(min(ncols, 15)):
            width = 22 if c < 10 else 16
            sheet.get_range_by_indexes(0, c, nrows, 1).format.column_width = width
        sheet.get_range_by_indexes(0, 0, nrows, min(ncols, 15)).format.wrap_text = True
    return sheet


def build():
    summary = json.loads((BASE / 'nnja_era5_erainterim_validated_summary.json').read_text(encoding='utf-8'))
    wb = Workbook.create()

    # README and summary.
    readme = wb.worksheets.add('README')
    rows = [
        ['NNJA / ERA5 / ERA-Interim validated daily comparison', ''],
        ['Comparison window', summary['comparison_window']],
        ['Calendar', '365-day no-leap calendar; one year = 365 days; D001-D365.'],
        ['ERA-Interim period', summary['era_interim_period']],
        ['ERA-Interim hard cap', 'ERA-Interim flags are clipped to 1979-01-01 through 2019-09-30.'],
        ['NNJA policy', 'Original pixel-derived NNJA records are used and clipped to 2025-D365.'],
        ['ERA extension policy', 'Post-source-edge ERA5 extensions are only carried forward after validation against retirement, service stops, and primary-satellite replacement records.'],
        ['Source figure right edge', f"{summary['era_source_right_edge_label']} / {summary['era_source_right_edge_date_365']}"],
        ['Label rule', 'Combination labels do not use parentheses, e.g. ERA5, NNJA.'],
        ['Validation rule', 'Extension_Validation records five independent checks per right-edge extension rule.'],
        ['Unique match keys', summary['unique_match_keys']],
        ['Comparison segments', summary['comparison_segments']],
        ['Daily long active rows', summary['daily_long_active_rows']],
        ['Day365 matrix rows', summary['matrix_rows']],
        ['Derived replacement rows', summary['derived_replacement_rows']],
        ['', ''],
        ['Category', 'Item-days'],
    ]
    for k, v in summary['category_day_counts'].items():
        rows.append([k, v])
    write_rows(readme, rows)
    readme.get_range('A1:B1').format = TITLE_FMT
    readme.get_range('A2:A15').format = LABEL_FMT
    readme.get_range('A17:B17').format = HEADER_FMT
    readme.get_range_by_indexes(0, 0, len(rows), 1).format.column_width = 36
    readme.get_range_by_indexes(0, 1, len(rows), 1).format.column_width = 92
    readme.get_range_by_indexes(0, 0, len(rows), 2).format.wrap_text = True

    add_csv_sheet(wb, 'Comparison_Segments', 'nnja_era5_erainterim_validated_inventory.csv')
    add_csv_sheet(wb, 'Key_Summary', 'nnja_era5_erainterim_validated_key_summary.csv')
    add_csv_sheet(wb, 'Extension_Validation', 'extension_validation.csv')
    add_csv_sheet(wb, 'Option_Definitions', 'option_definitions.csv')
    add_csv_sheet(wb, 'Code_Legend', 'code_legend.csv')
    add_csv_sheet(wb, 'Source_Files', 'source_files.csv')
    add_csv_sheet(wb, 'NNJA_Input', 'nnja_input_segments_normalized.csv')
    add_csv_sheet(wb, 'ERA_Input_Validated', 'era_input_segments_normalized_validated.csv')

    # Lightweight pointer sheet for the full matrix/long CSVs, avoiding a very heavy workbook.
    matrix_info = wb.worksheets.add('Daily_Files')
    daily_rows = [
        ['File', 'Description', 'Rows / notes'],
        ['nnja_era5_erainterim_validated_daily_365_matrix.csv', 'Full D001-D365 matrix with one record per match key and year.', summary['matrix_rows']],
        ['nnja_era5_erainterim_validated_daily_long.csv', 'Long-format active days; one row per active item-day.', summary['daily_long_active_rows']],
        ['Excel note', 'The full daily matrix and long table are included as CSVs in the package to keep the workbook responsive.', ''],
    ]
    write_rows(matrix_info, daily_rows)
    matrix_info.get_range('A1:C1').format = HEADER_FMT
    matrix_info.freeze_panes.freeze_rows(1)
    matrix_info.get_range_by_indexes(0, 0, len(daily_rows), 1).format.column_width = 46
    matrix_info.get_range_by_indexes(0, 1, len(daily_rows), 1).format.column_width = 80
    matrix_info.get_range_by_indexes(0, 2, len(daily_rows), 1).format.column_width = 24
    matrix_info.get_range_by_indexes(0, 0, len(daily_rows), 3).format.wrap_text = True

    return wb


if __name__ == '__main__':
    wb = build()
    print(wb.inspect({'kind': 'table', 'range': 'README!A1:B25', 'include': 'values,formulas', 'table_max_rows': 25, 'table_max_cols': 4}).ndjson)
    print(wb.inspect({'kind': 'match', 'search_term': '#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A', 'options': {'use_regex': True, 'max_results': 50}, 'summary': 'formula error scan'}).ndjson)
    SpreadsheetFile.export_xlsx(wb).save(str(OUT))
    print(str(OUT))
