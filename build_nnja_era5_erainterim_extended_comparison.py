#!/usr/bin/env python3
import csv, json, os, zipfile, importlib.util
from pathlib import Path
from collections import defaultdict, Counter

BASE_YEAR=1978
END_YEAR_EXCLUSIVE=2026
END_YEAR=2025
DAYS_PER_YEAR=365
START_DAY=1
END_DAY=(END_YEAR_EXCLUSIVE-BASE_YEAR)*365
MONTH_LENGTHS=[31,28,31,30,31,30,31,31,30,31,30,31]
OPTION_ORDER=['ERA5','ERA-Interim','NNJA','(ERA5, ERA-Interim, NNJA)','(ERA5, NNJA)','(ERA-Interim, NNJA)','only NNJA']
CATEGORY_ORDER=['ERA5','ERA-Interim','(ERA5, ERA-Interim)','(ERA5, ERA-Interim, NNJA)','(ERA5, NNJA)','(ERA-Interim, NNJA)','only NNJA']

spec=importlib.util.spec_from_file_location('oldbuild','/mnt/data/build_nnja_era5_daily_comparison.py')
old=importlib.util.module_from_spec(spec); spec.loader.exec_module(old)
parse_nnja_label=old.parse_nnja_label
parse_era_label=old.parse_era_label
canonical_item=old.canonical_item
infer_section=old.infer_section

def yday_to_md(doy):
    d=max(1,min(365,int(doy)))
    for m,ml in enumerate(MONTH_LENGTHS,1):
        if d<=ml: return m,d
        d-=ml
    return 12,31

def split_day(g):
    y=BASE_YEAR+(int(g)-1)//365
    doy=((int(g)-1)%365)+1
    m,d=yday_to_md(doy)
    return y,doy,f'{y}-D{doy:03d}',f'{y:04d}-{m:02d}-{d:02d}'

def absday(year,doy): return (int(year)-BASE_YEAR)*365+int(doy)
def interval(row): return absday(row['start_year'],row['start_day_of_year']), absday(row['end_year'],row['end_day_of_year'])
def sorted_join(vals): return '; '.join(sorted(set(str(v) for v in vals if str(v) not in ('','None'))))
def segids(payloads): return sorted_join(p.get('segment_id','') for p in payloads)

def era_flags(color):
    c=(color or '').lower().strip()
    if c in ('grey','gray','blue'): return True, True
    if c=='green': return True, False
    if c=='red': return False, True
    return False, False

def exact_cat(e5,ei,n):
    if e5 and ei and n: return '(ERA5, ERA-Interim, NNJA)'
    if e5 and ei: return '(ERA5, ERA-Interim)'
    if e5 and n: return '(ERA5, NNJA)'
    if ei and n: return '(ERA-Interim, NNJA)'
    if n: return 'only NNJA'
    if e5: return 'ERA5'
    if ei: return 'ERA-Interim'
    return ''

def opt_flags(e5,ei,n):
    o=[]
    if e5: o.append('ERA5')
    if ei: o.append('ERA-Interim')
    if n: o.append('NNJA')
    if e5 and ei and n: o.append('(ERA5, ERA-Interim, NNJA)')
    if e5 and n: o.append('(ERA5, NNJA)')
    if ei and n: o.append('(ERA-Interim, NNJA)')
    if n and not e5 and not ei: o.append('only NNJA')
    return '; '.join([x for x in OPTION_ORDER if x in o])

def add_range(map_,key,start,end,payload):
    s=max(START_DAY,int(start)); e=min(END_DAY,int(end))
    if e<s: return 0
    for day in range(s,e+1): map_[key][day].append(payload)
    return e-s+1

def read_csv(path):
    with open(path,newline='',encoding='utf-8') as f: return list(csv.DictReader(f))

def write_csv(path,rows,fields=None):
    if fields is None: fields=list(rows[0].keys()) if rows else []
    with open(path,'w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fields,extrasaction='ignore'); w.writeheader(); w.writerows(rows)

def build(nnja_path,era_path,out_dir):
    os.makedirs(out_dir,exist_ok=True)
    nnja=defaultdict(lambda:defaultdict(list)); era5=defaultdict(lambda:defaultdict(list)); erai=defaultdict(lambda:defaultdict(list))
    meta={}; nnja_in=[]; era_in=[]
    def ensure(key,sensor,sat,section=''):
        meta.setdefault(key,{'Sensor':sensor,'Satellite':sat,'Sensor_Sat':canonical_item(sensor,sat),'Section':section or infer_section(sensor),'NNJA_Source_Labels':set(),'ERA_Source_Labels':set()})
        if section: meta[key]['Section']=section
    for row in read_csv(nnja_path):
        sensor,sat=parse_nnja_label(row.get('row_label',''),row.get('source_path',''))
        key=f'{sensor}|{sat}'; ensure(key,sensor,sat); meta[key]['NNJA_Source_Labels'].add(row.get('row_label',''))
        s,e=interval(row)
        p={'source':'NNJA','segment_id':row.get('segment_id',''),'row_label':row.get('row_label',''),'code':row.get('code',''),'color':row.get('color',''),'thickness':row.get('thickness',''),'source_kind':row.get('source_kind','')}
        days=add_range(nnja,key,s,e,p)
        r=dict(row); r.update({'normalized_sensor':sensor,'normalized_satellite':sat,'match_key':key,'comparison_start_abs_day':max(s,START_DAY),'comparison_end_abs_day':min(e,END_DAY),'comparison_clipped_days':days}); nnja_in.append(r)
    era_rows=read_csv(era_path); era_edge=max(interval(r)[1] for r in era_rows)
    edge_y,edge_doy,edge_label,edge_date=split_day(era_edge)
    for row in era_rows:
        sensor,sat=parse_era_label(row.get('row_label',''))
        key=f'{sensor}|{sat}'; ensure(key,sensor,sat,row.get('section','')); meta[key]['ERA_Source_Labels'].add(row.get('row_label',''))
        s,e0=interval(row); extend=(e0==era_edge); e=END_DAY if extend else e0
        e5,ei=era_flags(row.get('color',''))
        p={'source':'ERA','segment_id':row.get('segment_id',''),'row_label':row.get('row_label',''),'code':row.get('code',''),'color':row.get('color',''),'thickness':row.get('thickness',''),'source_kind':row.get('source_kind',''),'original_end_abs_day':e0,'original_end_label':split_day(e0)[2],'extended_to_2025':extend}
        d5=add_range(era5,key,s,e,p) if e5 else 0; di=add_range(erai,key,s,e,p) if ei else 0
        r=dict(row); r.update({'normalized_sensor':sensor,'normalized_satellite':sat,'match_key':key,'era5_active':e5,'era_interim_active':ei,'era_source_right_edge_segment':extend,'original_end_abs_day':e0,'original_end_day_label':split_day(e0)[2],'extended_end_abs_day':min(e,END_DAY),'extended_end_day_label':split_day(min(e,END_DAY))[2],'comparison_clipped_days_era5':d5,'comparison_clipped_days_era_interim':di}); era_in.append(r)
    rows=[]
    for key in sorted(meta, key=lambda k:(meta[k]['Section'],meta[k]['Sensor'],meta[k]['Satellite'])):
        days=sorted(set(nnja.get(key,{}))|set(era5.get(key,{}))|set(erai.get(key,{})))
        cur=None; start=None; payload=None; prev=None
        def state(day):
            n=nnja.get(key,{}).get(day,[]); e5p=era5.get(key,{}).get(day,[]); eip=erai.get(key,{}).get(day,[])
            has_n,has_e5,has_ei=bool(n),bool(e5p),bool(eip)
            cat=exact_cat(has_e5,has_ei,has_n)
            if not cat: return None
            n_codes=tuple(sorted(set(p.get('code','') for p in n if p.get('code','')))); e5_codes=tuple(sorted(set(p.get('code','') for p in e5p if p.get('code','')))); ei_codes=tuple(sorted(set(p.get('code','') for p in eip if p.get('code',''))))
            n_ids=tuple(sorted(set(p.get('segment_id','') for p in n if p.get('segment_id','')))); e5_ids=tuple(sorted(set(p.get('segment_id','') for p in e5p if p.get('segment_id','')))); ei_ids=tuple(sorted(set(p.get('segment_id','') for p in eip if p.get('segment_id',''))))
            colors=tuple(sorted(set(p.get('color','') for p in e5p+eip if p.get('color','')))); kinds=tuple(sorted(set(p.get('source_kind','') for p in n if p.get('source_kind',''))))
            beyond=day>era_edge
            st=(cat,n_codes,e5_codes,ei_codes,n_ids,e5_ids,ei_ids,colors,kinds,beyond)
            pl={'n':n,'e5p':e5p,'eip':eip,'cat':cat,'opts':opt_flags(has_e5,has_ei,has_n),'has_n':has_n,'has_e5':has_e5,'has_ei':has_ei,'n_codes':'; '.join(n_codes),'e5_codes':'; '.join(e5_codes),'ei_codes':'; '.join(ei_codes),'colors':'; '.join(colors),'kinds':'; '.join(kinds),'beyond':beyond,'extended':any(p.get('extended_to_2025') for p in e5p+eip)}
            return st,pl
        def close(a,b,pl):
            sy,sd,sl,sdte=split_day(a); ey,ed,el,edte=split_day(b); m=meta[key]
            rows.append({'Sensor_Sat':m['Sensor_Sat'],'Sensor':m['Sensor'],'Satellite':m['Satellite'],'Section':m['Section'],'Match_Key':key,'Start_Date':sdte,'End_Date':edte,'Start_Day_Label':sl,'End_Day_Label':el,'Start_Abs_Day_365':a,'End_Abs_Day_365':b,'Duration_Days':b-a+1,'Exact_Category':pl['cat'],'Dataset_Category':pl['cat'],'Selection_Flags':pl['opts'],'NNJA_Active':pl['has_n'],'ERA5_Active':pl['has_e5'],'ERA_Interim_Active':pl['has_ei'],'NNJA_Codes':pl['n_codes'],'ERA5_Codes':pl['e5_codes'],'ERA_Interim_Codes':pl['ei_codes'],'ERA_Visible_Colors':pl['colors'],'NNJA_Source_Kinds':pl['kinds'],'NNJA_Segment_IDs':segids(pl['n']),'ERA5_Segment_IDs':segids(pl['e5p']),'ERA_Interim_Segment_IDs':segids(pl['eip']),'ERA_Extended_To_2025_Source_Segment':pl['extended'],'Beyond_ERA_Source_Edge':pl['beyond'],'ERA_Source_Right_Edge_Day_Label':edge_label,'ERA_Source_Right_Edge_Date_365':edge_date,'NNJA_Source_Labels':sorted_join(m['NNJA_Source_Labels']),'ERA_Source_Labels':sorted_join(m['ERA_Source_Labels']),'Calendar':'365_day_no_leap','Precision_Note':'day bins from pixel-derived endpoints; ERA right-edge bars extended to 2025-D365 by assumption'})
        for day in days:
            sp=state(day)
            if sp is None: continue
            st,pl=sp
            if cur is None: cur=st; start=day; payload=pl
            elif day!=prev+1 or st!=cur:
                close(start,prev,payload); cur=st; start=day; payload=pl
            prev=day
        if cur is not None: close(start,prev,payload)
    # dedupe + sort
    seen=set(); ded=[]
    for r in rows:
        key=(r['Match_Key'],r['Start_Abs_Day_365'],r['End_Abs_Day_365'],r['Exact_Category'],r['NNJA_Segment_IDs'],r['ERA5_Segment_IDs'],r['ERA_Interim_Segment_IDs'])
        if key not in seen: seen.add(key); ded.append(r)
    rows=sorted(ded,key=lambda r:(r['Section'],r['Sensor'],r['Satellite'],int(r['Start_Abs_Day_365']), CATEGORY_ORDER.index(r['Exact_Category']) if r['Exact_Category'] in CATEGORY_ORDER else 99))
    for i,r in enumerate(rows,1): r['Comparison_Segment_ID']=i
    fields=['Comparison_Segment_ID','Sensor_Sat','Sensor','Satellite','Section','Match_Key','Start_Date','End_Date','Start_Day_Label','End_Day_Label','Start_Abs_Day_365','End_Abs_Day_365','Duration_Days','Exact_Category','Dataset_Category','Selection_Flags','NNJA_Active','ERA5_Active','ERA_Interim_Active','NNJA_Codes','ERA5_Codes','ERA_Interim_Codes','ERA_Visible_Colors','NNJA_Source_Kinds','NNJA_Segment_IDs','ERA5_Segment_IDs','ERA_Interim_Segment_IDs','ERA_Extended_To_2025_Source_Segment','Beyond_ERA_Source_Edge','ERA_Source_Right_Edge_Day_Label','ERA_Source_Right_Edge_Date_365','NNJA_Source_Labels','ERA_Source_Labels','Calendar','Precision_Note']
    # key summary
    ksum=[]
    for key in sorted(meta,key=lambda k:(meta[k]['Section'],meta[k]['Sensor'],meta[k]['Satellite'])):
        rs=[r for r in rows if r['Match_Key']==key]
        if not rs: continue
        cnt=Counter(); ext=0
        for r in rs:
            d=int(r['Duration_Days']); cnt[r['Exact_Category']]+=d
            if str(r['Beyond_ERA_Source_Edge']).lower()=='true': ext+=d
        m=meta[key]
        ksum.append({'Match_Key':key,'Sensor_Sat':m['Sensor_Sat'],'Sensor':m['Sensor'],'Satellite':m['Satellite'],'Section':m['Section'],'NNJA_Source_Labels':sorted_join(m['NNJA_Source_Labels']),'ERA_Source_Labels':sorted_join(m['ERA_Source_Labels']),'ERA5_Days':sum(int(r['Duration_Days']) for r in rs if str(r['ERA5_Active']).lower()=='true'),'ERA_Interim_Days':sum(int(r['Duration_Days']) for r in rs if str(r['ERA_Interim_Active']).lower()=='true'),'NNJA_Days':sum(int(r['Duration_Days']) for r in rs if str(r['NNJA_Active']).lower()=='true'),'All_Three_Days':cnt['(ERA5, ERA-Interim, NNJA)'],'ERA5_NNJA_Days':cnt['(ERA5, NNJA)']+cnt['(ERA5, ERA-Interim, NNJA)'],'ERA_Interim_NNJA_Days':cnt['(ERA-Interim, NNJA)']+cnt['(ERA5, ERA-Interim, NNJA)'],'Only_NNJA_Days':cnt['only NNJA'],'ERA_Extension_Assumption_Days':ext,'Total_Active_Days':sum(int(r['Duration_Days']) for r in rs)})
    # matrix and long
    by=defaultdict(lambda:defaultdict(dict)); daily=[]
    for r in rows:
        for day in range(int(r['Start_Abs_Day_365']),int(r['End_Abs_Day_365'])+1):
            y,doy,lbl,ds=split_day(day); by[r['Match_Key']][y][doy]=r['Exact_Category']
            daily.append({'Sensor_Sat':r['Sensor_Sat'],'Sensor':r['Sensor'],'Satellite':r['Satellite'],'Section':r['Section'],'Match_Key':r['Match_Key'],'Date_365':ds,'Day_Label':lbl,'Abs_Day_365':day,'Year':y,'Day_Of_Year':doy,'Exact_Category':r['Exact_Category'],'Selection_Flags':r['Selection_Flags'],'NNJA_Active':r['NNJA_Active'],'ERA5_Active':r['ERA5_Active'],'ERA_Interim_Active':r['ERA_Interim_Active'],'Beyond_ERA_Source_Edge':r['Beyond_ERA_Source_Edge'],'Comparison_Segment_ID':r['Comparison_Segment_ID']})
    matrix=[]
    for key in sorted(by,key=lambda k:(meta[k]['Section'],meta[k]['Sensor'],meta[k]['Satellite'])):
        m=meta[key]
        for y in range(BASE_YEAR,END_YEAR_EXCLUSIVE):
            vals=by[key].get(y,{})
            if not vals: continue
            row={'Sensor_Sat':m['Sensor_Sat'],'Sensor':m['Sensor'],'Satellite':m['Satellite'],'Section':m['Section'],'Match_Key':key,'Year':y}
            for d in range(1,366): row[f'D{d:03d}']=vals.get(d,'')
            matrix.append(row)
    opts=[{'Option':'ERA5','Definition':'Any interval where ERA5 is active; overlaps are de-duplicated.','Exact_Filter_Expression':'ERA5_Active = TRUE'}, {'Option':'ERA-Interim','Definition':'Any interval where ERA-Interim is active; overlaps are de-duplicated.','Exact_Filter_Expression':'ERA_Interim_Active = TRUE'}, {'Option':'NNJA','Definition':'Any interval where NNJA is active, including pixel-derived short markers.','Exact_Filter_Expression':'NNJA_Active = TRUE'}, {'Option':'(ERA5, ERA-Interim, NNJA)','Definition':'Three-way overlap among ERA5, ERA-Interim, and NNJA.','Exact_Filter_Expression':'ERA5_Active AND ERA_Interim_Active AND NNJA_Active'}, {'Option':'(ERA5, NNJA)','Definition':'Intervals where ERA5 and NNJA are active.','Exact_Filter_Expression':'ERA5_Active AND NNJA_Active'}, {'Option':'(ERA-Interim, NNJA)','Definition':'Intervals where ERA-Interim and NNJA are active.','Exact_Filter_Expression':'ERA_Interim_Active AND NNJA_Active'}, {'Option':'only NNJA','Definition':'NNJA active while ERA5 and ERA-Interim are not active.','Exact_Filter_Expression':'NNJA_Active AND NOT ERA5_Active AND NOT ERA_Interim_Active'}]
    legend=[{'Code_or_Color':'grey','ERA5_Active':True,'ERA_Interim_Active':True,'Meaning':'used in both ERA5 and ERA-Interim'}, {'Code_or_Color':'blue','ERA5_Active':True,'ERA_Interim_Active':True,'Meaning':'ERA5 used reprocessed observations relative to ERA-Interim assimilated observations'}, {'Code_or_Color':'green','ERA5_Active':True,'ERA_Interim_Active':False,'Meaning':'used in ERA5 but not ERA-Interim'}, {'Code_or_Color':'red','ERA5_Active':False,'ERA_Interim_Active':True,'Meaning':'assimilated in ERA-Interim but not ERA5'}, {'Code_or_Color':'blue_thick / blue_thin','ERA5_Active':'','ERA_Interim_Active':'','Meaning':'NNJA visible blue bar'}, {'Code_or_Color':'black_thick / black_marker','ERA5_Active':'','ERA_Interim_Active':'','Meaning':'NNJA visible black bar or one-day marker'}]
    sources=[{'Source':'NNJA','Path':nnja_path,'Policy':'Use original pixel-derived NNJA endpoints; clip to 2025-D365.'}, {'Source':'ERA','Path':era_path,'Policy':'Extend ERA bars touching the rightmost extracted ERA time boundary to 2025-D365.'}, {'Source':'Calendar','Path':'','Policy':'365_day_no_leap; one year = 365 days; no leap day.'}]
    out=Path(out_dir)
    write_csv(out/'nnja_era5_erainterim_extended_inventory.csv',rows,fields)
    write_csv(out/'nnja_era5_erainterim_extended_key_summary.csv',ksum)
    write_csv(out/'nnja_era5_erainterim_extended_daily_365_matrix.csv',matrix,['Sensor_Sat','Sensor','Satellite','Section','Match_Key','Year']+[f'D{d:03d}' for d in range(1,366)])
    write_csv(out/'nnja_era5_erainterim_extended_daily_long.csv',daily)
    write_csv(out/'nnja_input_segments_normalized.csv',nnja_in)
    write_csv(out/'era_input_segments_normalized_extended.csv',era_in)
    write_csv(out/'option_definitions.csv',opts)
    write_csv(out/'code_legend.csv',legend)
    write_csv(out/'source_files.csv',sources)
    summary={'base_year':BASE_YEAR,'end_year_exclusive':END_YEAR_EXCLUSIVE,'comparison_window':f'{BASE_YEAR}-D001..{END_YEAR}-D365','nnja_input_segments':len(nnja_in),'era_input_segments':len(era_in),'era_source_right_edge_abs_day':era_edge,'era_source_right_edge_label':edge_label,'era_source_right_edge_date_365':edge_date,'unique_match_keys':len(ksum),'comparison_segments':len(rows),'daily_long_active_rows':len(daily),'matrix_rows':len(matrix),'category_day_counts':{cat:sum(int(r['Duration_Days']) for r in rows if r['Exact_Category']==cat) for cat in CATEGORY_ORDER},'extension_days':sum(int(r['Duration_Days']) for r in rows if str(r['Beyond_ERA_Source_Edge']).lower()=='true')}
    with open(out/'nnja_era5_erainterim_extended_summary.json','w',encoding='utf-8') as f: json.dump(summary,f,indent=2,ensure_ascii=False)
    return summary

if __name__=='__main__':
    s=build('/mnt/data/full_nnja_daily/all_line_segments_daily_units.csv','/mnt/data/era_da_daily/era_da_observation_inventory_segments_daily_units.csv','/mnt/data/nnja_era5_erainterim_extended')
    print(json.dumps(s,indent=2,ensure_ascii=False))
