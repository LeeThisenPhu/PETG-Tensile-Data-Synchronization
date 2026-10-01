from pathlib import Path
import os,re,json,collections,sys
import numpy as np,pandas as pd
ROOT=Path(__file__).resolve().parents[1]
OUT=Path(os.environ.get('PETG420_OUTPUT',str(ROOT/'output'))).resolve()
from processing import read_mt

def read_terminal(path):
    rows=[];bad=[]
    rx=r'\s*(?:\d{4}\.\d{2}\.\d{2},\s*)?(?:(\d{1,2}:\d{2}:\d{2}(?:[.,]\d+)?)\s*,?\s*)?([+-]?)\s*(\d+(?:[.,]\d+)?)\s*kg\s*'
    for i,line in enumerate(path.read_text(encoding='utf-8-sig',errors='replace').splitlines(),1):
        m=re.fullmatch(rx,line,re.I)
        if m:
            ts=m[1];t=np.nan
            if ts:
                a,b,c=ts.replace(',','.').split(':');t=int(a)*3600+int(b)*60+float(c)
            rows.append([i,ts,t,(-1 if m[2]=='-' else 1)*float(m[3].replace(',','.'))])
        elif i>3 and line.strip() and not(line.startswith('---') or line.startswith('Date:') or line.strip()=='End log file'):bad.append([i,line])
    if not rows:raise ValueError('No terminal force')
    df=pd.DataFrame(rows,columns=['source_line','timestamp_raw','clock_s','force_kg'])
    return df,bad

def pairs():
    for g in range(1,85):
        for n in range(1,6):
            group=f'G{g:03}';sid=f'{group}_{n}';folder=OUT/'source/Data_mau_thu'/group/str(n)
            mp=list(folder.glob('*.txt'));tp=list(folder.glob('*.log'))
            if len(mp)!=1 or len(tp)!=1:raise ValueError(f'Pair count {sid}')
            yield sid,mp[0],tp[0]

def main():
    records=[]
    for sid,mp,tp in pairs():
        try:
            h,m=read_mt(mp);t,bad=read_terminal(tp)
            records.append(dict(sample=sid,mt_n=len(m),ter_n=len(t),time_end=m.Time.iloc[-1],mt_dt=np.median(np.diff(m.Time)),mt_maxgap=np.diff(m.Time).max(),timestamp_n=t.clock_s.notna().sum(),timestamp_duplicates=np.sum(np.diff(t.clock_s)==0),timestamp_backwards=np.sum(np.diff(t.clock_s)<0),terminal_clock_duration=t.clock_s.iloc[-1]-t.clock_s.iloc[0],terminal_clock_maxgap=np.nanmax(np.diff(t.clock_s)) if t.clock_s.notna().any() else None,force_max=t.force_kg.max(),force_last=t.force_kg.iloc[-1],load_max=m.Load.max(),elong_min=m.Elong.min(),elong_max=m.Elong.max(),elong_equals_disp=bool(np.allclose(m.Elong,m.Disp,atol=1e-8)),bad_lines=bad,header=h,maxtest_file=mp.relative_to(OUT).as_posix(),terminal_file=tp.relative_to(OUT).as_posix()))
        except Exception as e:records.append(dict(sample=sid,error=str(e)))
    (OUT/'raw_audit.json').write_text(json.dumps(records,ensure_ascii=False,indent=2,default=lambda o:o.item() if hasattr(o,'item') else str(o)),encoding='utf-8')
    df=pd.DataFrame(records);df.drop(columns=['header','bad_lines']).to_csv(OUT/'raw_audit.csv',index=False,encoding='utf-8-sig')
    print('n',len(records),'errors',[r for r in records if 'error' in r])
    print(df[['mt_n','ter_n','mt_dt','timestamp_n','timestamp_duplicates','timestamp_backwards','force_max','mt_maxgap']].describe().to_string())
    print('No timestamps',df.loc[df.timestamp_n==0,'sample'].tolist())
    print('Elong == Disp',df.loc[df.elong_equals_disp==True,'sample'].tolist())
    print('Bad terminal lines',[(r['sample'],r['bad_lines'][:3]) for r in records if r.get('bad_lines')])
    print('Dimensions',collections.Counter((r.get('header',{}).get('Size(mm)'),r.get('header',{}).get('Lo(mm)')) for r in records))
    w=json.loads((OUT/'input_workbook.json').read_text(encoding='utf-8'))
    print('Workbook sheets',list(w))
    for name,vals in w.items():
        if name=='Ghi số liệu':print('Input dimensions',collections.Counter(str(row[6:8]) for row in vals[3:] if isinstance(row[0],str) and re.fullmatch('G[0-9]{3}',row[0])))
if __name__=='__main__':main()
