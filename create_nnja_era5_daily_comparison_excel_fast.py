#!/usr/bin/env python3
import csv, json, os
from artifact_tool import Workbook, SpreadsheetFile
OUT_DIR='/mnt/data/nnja_era5_daily_comparison'
OUT_XLSX=os.path.join(OUT_DIR,'nnja_era5_daily_comparison.xlsx')
HEADER_FMT={'fill':'#1F4E78','font':{'bold':True,'color':'#FFFFFF'},'horizontal_alignment':'center','vertical_alignment':'center','wrap_text':True}
SUBHEADER_FMT={'fill':'#D9EAF7','font':{'bold':True,'color':'#1F2937'},'wrap_text':True}
TITLE_FMT={'font':{'bold':True,'size':16,'color':'#1F4E78'}}
TEXT_FMT={'wrap_text':True,'vertical_alignment':'top'}
def read_csv_rows(path):
    with open(path,newline='',encoding='utf-8') as f:
        r=csv.DictReader(f); rows=list(r); return r.fieldnames, rows
def write_matrix(sheet, start_row, start_col, matrix):
    if not matrix: return
    sheet.get_range_by_indexes(start_row,start_col,len(matrix),len(matrix[0])).values=matrix
def matrix_from_rows(headers, rows):
    return [headers]+[[row.get(h,'') for h in headers] for row in rows]
def style_table(sheet,nrows,ncols,widths=None,table_name=None):
    if not nrows or not ncols: return
    sheet.get_range_by_indexes(0,0,1,ncols).format=HEADER_FMT
    sheet.get_range_by_indexes(0,0,1,ncols).format.row_height=30
    if nrows>1:
        sheet.get_range_by_indexes(1,0,nrows-1,ncols).format=TEXT_FMT
    sheet.freeze_panes.freeze_rows(1)
    if widths:
        for col_idx,width in widths.items():
            if col_idx<ncols:
                sheet.get_range_by_indexes(0,col_idx,nrows,1).format.column_width=width
    if table_name:
        try:
            sheet.tables.add(sheet.get_range_by_indexes(0,0,nrows,ncols), True, table_name)
        except Exception:
            pass

def main():
    with open(os.path.join(OUT_DIR,'nnja_era5_daily_comparison_summary.json'),encoding='utf-8') as f: summary=json.load(f)
    wb=Workbook.create()
    # README
    sh=wb.worksheets.add('README')
    rows=[
        ['NNJA vs ERA5 DA daily comparison inventory',''],['',''],
        ['Purpose','Replaces the old nnja_era5_full_inventory_v7.csv workflow with day-level intervals built from the pixel-extracted NNJA and ERA bars.'],
        ['Comparison window',summary['comparison_window']],
        ['Calendar','Fixed 365-day years, D001..D365, no leap day.'],
        ['NNJA active','Any NNJA pixel-derived line segment, including one-day black markers.'],
        ['ERA5 DA active','ERA colors grey, green, or blue. Blue is treated as ERA5 DA active because it is reprocessed relative to ERA-Interim observations.'],
        ['ERA-Interim only','ERA red bars. These are kept as a separate flag/status and not counted as ERA5 DA overlap.'],
        ['De-duplication','Data are grouped by normalized sensor + satellite key and split into non-overlapping daily intervals. Multiple source bars for the same item/day are unioned.'],
        ['Precision','Endpoints are daily bins from pixel-derived raster positions; ERA figure is clipped to 1978-D001..2019-D365.'],
        ['',''],['Input NNJA segments',summary['nnja_input_segments']],['Input ERA segments',summary['era_input_segments']],['Unique matched item keys',summary['unique_match_keys']],['Output comparison intervals',summary['comparison_segments']],['Active daily long rows in CSV',summary['daily_long_active_rows']],['Day365 matrix rows in CSV',summary['matrix_rows']],['',''],['Status day counts','Item-days']]
    for k,v in summary['status_day_counts'].items(): rows.append([k,v])
    write_matrix(sh,0,0,rows)
    sh.get_range('A1:B1').format=TITLE_FMT
    sh.get_range('A3:A30').format=SUBHEADER_FMT
    sh.get_range('A:A').format.column_width=30
    sh.get_range('B:B').format.column_width=110
    sh.get_range('A1:B40').format.wrap_text=True
    # Code legend and matching rules
    legend=[['Code / Status','Meaning'],['Both','NNJA active and ERA5 DA active in the same daily interval.'],['NNJA Only','NNJA active, no ERA5 DA active bar.'],['ERA5 Only','ERA5 DA active, no matching NNJA active item.'],['ERA-Interim Only (not ERA5)','Red ERA bars: assimilated in ERA-Interim but not ERA5.'],['grey','Used in both ERA5 and ERA-Interim.'],['green','Used in ERA5 but not ERA-Interim.'],['blue','Reprocessed relative to ERA-Interim observations; treated as ERA5 DA active.'],['red','ERA-Interim only, not ERA5.'],['black_marker','One-day NNJA vertical marker retained from pixel extraction.']]
    shl=wb.worksheets.add('Code_Legend'); write_matrix(shl,0,0,legend); style_table(shl,len(legend),2,{0:34,1:100},'CodeLegendTable')
    rules=[['Rule','Implementation'],['Normalized key','Sensor + satellite after normalization.'],['AMSU-A / AMSUA','Normalized to AMSUA.'],['AMSU-B / AMSUB','Normalized to AMSUB.'],['AMSR-2 / AMSR2','Normalized to AMSR-2.'],['AMSR-E / AMSRE','Normalized to AMSRE.'],['METEOSAT 8-11 GEOS Rad.','Mapped to SEVIRI to match NNJA SEVIRI rows.'],['TRMM row in NNJA','NNJA trmm TRMM is matched to ERA TRMM TMI as TMI (TRMM).'],['GPM-core','Normalized to GPM.'],['SAPHIR','ERA SAPHIR All-sky matched to NNJA saphir Megha-Tropiques.'],['ERA5 colors','grey, green, blue are ERA5 active; red is ERA-Interim-only.'],['Interval construction','Source days are unioned and split only when status or source-code sets change.']]
    shr=wb.worksheets.add('Matching_Rules'); write_matrix(shr,0,0,rules); style_table(shr,len(rules),2,{0:36,1:110},'MatchingRulesTable')
    # Main data sheets. Keep matrix/daily-long as CSV to preserve workbook responsiveness.
    specs=[
        ('Comparison_Segments','nnja_era5_daily_comparison_inventory.csv','ComparisonSegmentsTable',{0:12,1:30,2:12,3:18,4:28,5:20,6:12,7:12,8:14,9:14,10:14,11:14,12:12,13:34,14:18,18:32,19:32,20:32,26:60,27:60,29:80}),
        ('Key_Summary','nnja_era5_daily_key_summary.csv','KeySummaryTable',{0:20,1:30,2:12,3:18,4:28,5:60,6:70,7:12,8:14,9:14,10:18,11:16}),
        ('NNJA_Input','nnja_input_segments_normalized.csv',None,{0:12,2:12,3:24,4:32,5:10,6:10,7:16,24:20,25:20,26:20}),
        ('ERA_Input','era_input_segments_normalized.csv',None,{0:12,2:32,3:28,5:10,6:10,7:16,8:60,30:20,31:20,32:20})]
    for sname,fn,tname,widths in specs:
        headers,rowsdata=read_csv_rows(os.path.join(OUT_DIR,fn))
        shd=wb.worksheets.add(sname)
        matrix=matrix_from_rows(headers,rowsdata)
        write_matrix(shd,0,0,matrix)
        style_table(shd,len(matrix),len(headers),widths,tname)
    src=[['File','Description'],['nnja_era5_daily_comparison_inventory.csv','Replacement data file read by the modified Streamlit app.'],['nnja_era5_daily_365_matrix.csv','Full D001-D365 matrix by sensor/satellite/year.'],['nnja_era5_daily_long.csv','Active daily long rows, kept as CSV because it has many rows.'],['nnja_input_segments_normalized.csv','Normalized NNJA pixel-derived source segments.'],['era_input_segments_normalized.csv','Normalized ERA pixel-derived source segments.']]
    shs=wb.worksheets.add('Source_Files'); write_matrix(shs,0,0,src); style_table(shs,len(src),2,{0:50,1:110},'SourceFilesTable')
    print(wb.inspect({'kind':'table','range':'README!A1:B24','include':'values','table_max_rows':24,'table_max_cols':2}).ndjson)
    print(wb.inspect({'kind':'match','search_term':'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A','options':{'use_regex':True,'max_results':100},'summary':'formula error scan'}).ndjson)
    SpreadsheetFile.export_xlsx(wb).save(OUT_XLSX)
    print('saved',OUT_XLSX)
if __name__=='__main__': main()
