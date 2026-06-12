#!/usr/bin/env python3
import csv, json, os
from pathlib import Path
from artifact_tool import Workbook, SpreadsheetFile

OUT_DIR=Path('/mnt/data/nnja_era5_erainterim_extended')
OUT_XLSX=OUT_DIR/'nnja_era5_erainterim_extended_comparison.xlsx'
HEADER_FMT={'fill':'#1F4E78','font':{'bold':True,'color':'#FFFFFF'},'horizontal_alignment':'center','vertical_alignment':'center','wrap_text':True}
SUBHEADER_FMT={'fill':'#D9EAF7','font':{'bold':True,'color':'#1F2937'},'wrap_text':True}
TITLE_FMT={'font':{'bold':True,'size':16,'color':'#1F4E78'}}
TEXT_FMT={'wrap_text':True,'vertical_alignment':'top'}

def read_csv_rows(path):
    with open(path,newline='',encoding='utf-8') as f:
        r=csv.DictReader(f); rows=list(r); return r.fieldnames, rows

def write_matrix(sheet, start_row, start_col, matrix):
    if matrix: sheet.get_range_by_indexes(start_row,start_col,len(matrix),len(matrix[0])).values=matrix

def matrix_from_rows(headers, rows):
    return [headers]+[[row.get(h,'') for h in headers] for row in rows]

def style_table(sheet,nrows,ncols,widths=None,table_name=None):
    if not nrows or not ncols: return
    sheet.get_range_by_indexes(0,0,1,ncols).format=HEADER_FMT
    sheet.get_range_by_indexes(0,0,1,ncols).format.row_height=32
    if nrows>1: sheet.get_range_by_indexes(1,0,nrows-1,ncols).format=TEXT_FMT
    sheet.freeze_panes.freeze_rows(1)
    if widths:
        for col_idx,width in widths.items():
            if col_idx<ncols: sheet.get_range_by_indexes(0,col_idx,nrows,1).format.column_width=width
    if table_name:
        try: sheet.tables.add(sheet.get_range_by_indexes(0,0,nrows,ncols), True, table_name)
        except Exception: pass

def main():
    with open(OUT_DIR/'nnja_era5_erainterim_extended_summary.json',encoding='utf-8') as f: summary=json.load(f)
    wb=Workbook.create()
    sh=wb.worksheets.add('README')
    rows=[
        ['NNJA / ERA5 / ERA-Interim daily comparison inventory',''],['',''],
        ['Purpose','Compare normalized sensor/satellite items among NNJA, ERA5, and ERA-Interim using daily bins derived from pixel-extracted line segments.'],
        ['Comparison window',summary['comparison_window']],
        ['Calendar','Fixed 365-day years, D001..D365, no leap day.'],
        ['NNJA policy','Use original pixel-derived NNJA endpoints, clipped to 2025-D365.'],
        ['ERA policy','ERA bars touching the rightmost extracted ERA time boundary are extended to 2025-D365 by assumption.'],
        ['ERA source right edge detected from pixels',f"{summary['era_source_right_edge_label']} / {summary['era_source_right_edge_date_365']}"],
        ['Color interpretation','grey and blue = ERA5 plus ERA-Interim; green = ERA5 only; red = ERA-Interim only.'],
        ['De-duplication','Rows are grouped by normalized sensor + satellite key and split into non-overlapping daily intervals. App selected options are unioned and duplicate rows are dropped.'],
        ['Pixel endpoints','Short pixel-derived intervals and one-day NNJA markers are preserved as day-level breakpoints.'],
        ['',''],['Input NNJA segments',summary['nnja_input_segments']],['Input ERA segments',summary['era_input_segments']],['Unique matched item keys',summary['unique_match_keys']],['Output comparison intervals',summary['comparison_segments']],['Active daily long rows in CSV',summary['daily_long_active_rows']],['Day365 matrix rows in CSV',summary['matrix_rows']],['ERA extension-assumption item-days',summary['extension_days']],['',''],['Exact category day counts','Item-days']]
    for k,v in summary['category_day_counts'].items(): rows.append([k,v])
    write_matrix(sh,0,0,rows)
    sh.get_range('A1:B1').format=TITLE_FMT
    sh.get_range('A3:A35').format=SUBHEADER_FMT
    sh.get_range('A:A').format.column_width=38
    sh.get_range('B:B').format.column_width=120
    sh.get_range('A1:B60').format.wrap_text=True
    specs=[
        ('Comparison_Segments','nnja_era5_erainterim_extended_inventory.csv','ComparisonSegmentsTable',{0:12,1:30,2:12,3:18,4:28,5:20,6:12,7:12,8:14,9:14,10:14,11:14,12:12,13:34,15:60,19:24,20:24,21:24,22:18,24:18,25:18,26:18,31:70,32:70,34:100}),
        ('Key_Summary','nnja_era5_erainterim_extended_key_summary.csv','KeySummaryTable',{0:20,1:30,2:12,3:18,4:28,5:60,6:70,7:12,8:14,9:14,10:16,11:16,12:18,13:14,14:18,15:16}),
        ('Option_Definitions','option_definitions.csv','OptionDefinitionsTable',{0:36,1:120,2:70}),
        ('Code_Legend','code_legend.csv','CodeLegendTable',{0:32,1:14,2:18,3:120}),
        ('Source_Files','source_files.csv','SourceFilesTable',{0:18,1:80,2:120}),
        ('NNJA_Input','nnja_input_segments_normalized.csv',None,{0:12,2:12,3:24,4:32,5:10,6:10,7:16,24:20,25:20,26:20}),
        ('ERA_Input','era_input_segments_normalized_extended.csv',None,{0:12,2:32,3:28,5:10,6:10,7:16,8:60,30:20,31:20,32:20}),
    ]
    for sname,fn,tname,widths in specs:
        headers,data=read_csv_rows(OUT_DIR/fn)
        sheet=wb.worksheets.add(sname)
        matrix=matrix_from_rows(headers,data)
        write_matrix(sheet,0,0,matrix)
        style_table(sheet,len(matrix),len(headers),widths,tname)
    print(wb.inspect({'kind':'table','range':'README!A1:B25','include':'values','table_max_rows':25,'table_max_cols':2}).ndjson)
    print(wb.inspect({'kind':'match','search_term':'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A','options':{'use_regex':True,'max_results':100},'summary':'formula error scan'}).ndjson)
    SpreadsheetFile.export_xlsx(wb).save(str(OUT_XLSX))
    print('saved',OUT_XLSX)
if __name__=='__main__': main()
