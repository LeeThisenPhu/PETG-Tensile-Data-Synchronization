"""Synchronize Maxtest displacement with Terminal force for PETG tensile tests."""
from pathlib import Path
import os,re,json,sys,argparse
import numpy as np,pandas as pd
from scipy.ndimage import median_filter
PROJECT_ROOT=Path(__file__).resolve().parents[1]
OUT=Path(os.environ.get('PETG420_OUTPUT',str(PROJECT_ROOT/'output'))).resolve()
G0=9.80665; L0=50.; WIDTH=10.; THICKNESS=4.; AREA=40.

def read_mt(path):
    lines=path.read_bytes().decode('latin1').splitlines()
    k=next(i for i,x in enumerate(lines) if x.startswith('Time\t'))
    head=dict(x.split('\t',1) for x in lines[:k] if '\t' in x)
    rows=[[float(x.replace(',','.')) for x in line.split('\t')] for line in lines[k+1:] if line.strip()]
    df=pd.DataFrame(rows,columns=lines[k].split('\t'))
    if not np.isfinite(df[['Time','Load','Elong']]).all().all():raise ValueError('Maxtest nonfinite')
    if np.any(np.diff(df.Time)<=0):raise ValueError('Maxtest nonincreasing time')
    return head,df

def read_terminal(path):
    rows=[];bad=[]
    rx=r'\s*(?:\d{4}\.\d{2}\.\d{2},\s*)?(?:(\d{1,2}:\d{2}:\d{2}(?:[.,]\d+)?)\s*,?\s*)?([+-]?)\s*(\d+(?:[.,]\d+)?)\s*kg\s*'
    for i,line in enumerate(path.read_text(encoding='utf-8-sig',errors='replace').splitlines(),1):
        m=re.fullmatch(rx,line,re.I)
        if m:
            ts=m[1];t=np.nan
            if ts:
                h,mi,sec=ts.replace(',','.').split(':');t=int(h)*3600+int(mi)*60+float(sec)
            rows.append([i,ts,t,(-1 if m[2]=='-' else 1)*float(m[3].replace(',','.'))])
        elif i>3 and line.strip() and not(line.startswith('---') or line.startswith('Date:') or line.strip()=='End log file'):
            bad.append(dict(source_line=i,raw_text=line,reason='Dòng không hoàn chỉnh hoặc ghép nhiều khung; không suy đoán số lực'))
    if not rows:raise ValueError('No terminal force')
    return pd.DataFrame(rows,columns=['source_line','timestamp_raw','clock_s','force_kg']),bad

def pairs():
    for g in range(1,85):
        for n in range(1,6):
            group=f'G{g:03}';sid=f'{group}_{n}';folder=OUT/'source/Data_mau_thu'/group/str(n)
            mp=list(folder.glob('*.txt'));tp=list(folder.glob('*.log'))
            if len(mp)!=1 or len(tp)!=1:raise ValueError(f'Pair count {sid}')
            yield sid,mp[0],tp[0]

def metadata():
    w=json.loads((OUT/'input_workbook.json').read_text(encoding='utf-8'))
    d={}
    for row in w['Ma trận thực nghiệm']:
        if isinstance(row[0],str) and re.fullmatch(r'G\d{3}',row[0]) and int(row[0][1:])<=84:
            d[row[0]]=dict(group=row[0],angle_deg=row[1],layer_mm=row[2],infill_pct=row[3],pattern=row[4],test_speed_mm_min=2.,source_speed_excel_mm_min=row[6],print_date=row[11],printing_notes=row[10])
    if len(d)!=84:raise ValueError('Matrix mapping !=84')
    return d

def norm(f):
    b=float(np.median(f[:min(3,len(f))]));am=float(np.quantile(f,.995)-b)
    if am<=0:raise ValueError('No force amplitude')
    return (f-b)/am,b,am

def onset(f,t=None):
    count=max(1,min(10,int(.25/np.median(np.diff(t)))+1)) if t is not None else min(3,len(f))
    base=float(np.median(f[:count]));am=float(np.quantile(f,.995)-base);noise=1.4826*np.median(np.abs(f[:count]-base))
    threshold=base+max(5*noise,.005*am,.25)
    for i in range(1,len(f)-2):
        if np.all(f[i:i+3]>threshold):return i,threshold
    raise ValueError('No onset')

def drop_anchor(t,f):
    # Median used for timing diagnostics only; exported force and UTS remain raw.
    fs=median_filter(f,size=3,mode='nearest');near=np.flatnonzero(fs>=.9*np.quantile(fs,.995));peak=int(near[-1])
    if peak>=len(f)-2:return float(t[-1]),len(f)-2,0.,fs
    falls=fs[:-1]-fs[1:]
    k=peak+int(np.argmax(falls[peak:]));amount=float(fs[k]-fs[k+1])
    return .5*(t[k]+t[k+1]),k,amount,fs

def terminal_axis(df):
    raw=df.clock_s.to_numpy();n=len(raw)
    if np.isfinite(raw).all():
        # Retain acquisition order. Midnight wraps are separate from short receipt-time reversals.
        t=raw.copy();day=0.
        for i in range(1,n):
            if raw[i]-raw[i-1]<-43200:day+=86400
            t[i]+=day
        backwards=int(np.sum(np.diff(t)<0));duplicates=int(np.sum(np.diff(t)==0))
        axis=np.maximum.accumulate(t)
        # Spread a duplicate/nonmonotone receipt-time batch between surrounding clock anchors.
        starts=np.r_[0,np.flatnonzero(np.diff(axis)>0)+1]
        ends=np.r_[starts[1:]-1,n-1]
        positive=np.diff(t)[np.diff(t)>0];dt=float(np.median(positive)) if len(positive) else .125
        for start,end in zip(starts,ends):
            if end>start:
                before=axis[start-1] if start>0 else axis[start]-dt*(end-start+1)
                axis[start:end+1]=np.linspace(before,axis[start],end-start+2)[1:]
        if np.any(np.diff(axis)<=0):raise ValueError('Unrepairable receipt times')
        adjusted=int(np.sum(np.abs(axis-t)>1e-9))
        return axis-axis[0],dict(time_basis='TIMESTAMP_LOCAL_RECONSTRUCTION',timestamp_adjusted_n=adjusted,timestamp_backwards_n=backwards,timestamp_duplicates_n=duplicates,terminal_clock_duration_s=float(t[-1]-t[0]))
    if np.isfinite(raw).any():raise ValueError('Mixed timestamp coverage')
    # Preserve source line gaps: malformed measurement lines consume positions rather than compressing time.
    axis=df.source_line.to_numpy(dtype=float);axis-=axis[0]
    return axis,dict(time_basis='RECONSTRUCTED_SOURCE_LINE_INDEX',timestamp_adjusted_n=0,timestamp_backwards_n=0,timestamp_duplicates_n=0,terminal_clock_duration_s=None)

def crossing(t,f,q):
    ids=np.flatnonzero(f>=q)
    if not len(ids):return np.nan
    j=int(ids[0]);return float(t[0]) if j==0 else float(np.interp(q,f[j-1:j+1],t[j-1:j+1]))

def alignment(mt,ter):
    tm=mt.Time.to_numpy();fm=mt.Load.to_numpy()*1000/G0;ft=ter.force_kg.to_numpy()
    axis,extra=terminal_axis(ter)
    am,km,dm,fms=drop_anchor(tm,fm);at,kt,dt,fts=drop_anchor(axis,ft)
    # A truncated MT trace can still be aligned at fracture with recorded Terminal time,
    # but cannot establish a valid extensometer zero or the missing initial curve.
    partial=float(np.median(fm[:min(5,len(fm))]))>max(2.,.1*np.quantile(fm,.995))
    im,thm=onset(fm,tm) if not partial else (0,None)
    it,tht=onset(fts,axis if extra['time_basis']=='TIMESTAMP_LOCAL_RECONSTRUCTION' else None)
    weak=dm<.1*np.quantile(fm,.995) or dt<.1*np.quantile(fts,.995)
    if partial:
        if extra['time_basis']!='TIMESTAMP_LOCAL_RECONSTRUCTION':raise ValueError('Truncated MT and no Terminal timestamps')
        scale=1.;offset=am-at;method='FRACTURE_ONLY_PARTIAL_MT'
    elif weak and extra['time_basis']=='TIMESTAMP_LOCAL_RECONSTRUCTION':
        scale=1.;offset=tm[im]-axis[it];method='ONSET_ONLY_NO_SHARP_FRACTURE'
    elif weak:
        # Restricted linear fallback: onset is fixed, 10–60% landmarks fit scale.
        # 70–90% landmarks are withheld from fitting; always flagged as a fallback.
        fnm,_,_=norm(fms);fnt,_,_=norm(fts)
        ratios=[]
        for q in np.arange(.1,.61,.1):
            dx=crossing(axis,fnt,q)-axis[it];dy=crossing(tm,fnm,q)-tm[im]
            if dx>0 and dy>0:ratios.append(dy/dx)
        if len(ratios)<4:raise ValueError('Không đủ mốc lực để ước lượng tuyến tính')
        scale=float(np.median(ratios));offset=tm[im]-scale*axis[it];method='ONSET_AND_RISING_FORCE_FALLBACK'
    else:
        scale=(am-tm[im])/(at-axis[it]);offset=tm[im]-scale*axis[it];method='ONSET_AND_FRACTURE'
    if scale<=0:raise ValueError('Negative mapping scale')
    if extra['time_basis']=='TIMESTAMP_LOCAL_RECONSTRUCTION' and not .8<=scale<=1.25:
        raise ValueError(f'Khoảng onset–gãy không tương thích timestamp (hệ số {scale:.3f}); không ép kéo giãn thời gian. Kiểm tra ghép cặp hoặc bản ghi bị thiếu.')
    tt=offset+scale*axis
    fmn,_,_=norm(fms);ftn,_,_=norm(fts)
    validation_levels=[.7,.8,.9] if method=='ONSET_AND_RISING_FORCE_FALLBACK' else np.arange(.1,.81,.1)
    residual=[crossing(tt,ftn,q)-crossing(tm,fmn,q) for q in validation_levels] if not partial else []
    mask=(tt>=tm[im])&(tt<am-.5)&(tt<=tm[-1])
    rmse=float(np.sqrt(np.mean((ftn[mask]-np.interp(tt[mask],tm,fmn))**2))) if np.any(mask) and not partial else None
    return tt,dict(**extra,sync_method=method,time_scale=float(scale),offset_s=float(offset),effective_rate_hz=float((len(tt)-1)/(tt[-1]-tt[0])),mt_onset_s=float(tm[im]),mt_onset_index=im,terminal_onset_index=it,mt_drop_s=float(am),mt_drop_index=km,terminal_drop_axis=float(at),terminal_drop_index=kt,mt_drop_size=dm,terminal_drop_size=dt,partial_maxtest=partial,rmse_normalized=rmse,max_landmark_residual_s=float(np.nanmax(np.abs(residual))) if residual else None,landmark_residual_s=residual,validation_force_fractions=list(validation_levels))

def interp_safe(q,t,y):
    v=np.interp(q,t,y,left=np.nan,right=np.nan)
    right=np.searchsorted(t,q);inside=(right>0)&(right<len(t));k=np.flatnonzero(inside);r=right[k]
    gap=t[r]-t[r-1]>5*np.median(np.diff(t));exact=np.isclose(q[k],t[r],atol=1e-9,rtol=0)
    v[k[gap&~exact]]=np.nan
    return v

def cutoff(mt,mapping):
    tm=mt.Time.to_numpy();f=mt.Load.to_numpy();e=mt.Elong.to_numpy();k=mapping['mt_drop_index']
    slope=np.diff(f)/np.diff(tm);threshold=max(.1*abs(slope[k]),.08*f.max()/np.median(np.diff(tm)))
    start=k
    while start>0 and tm[k]-tm[start]<.4 and slope[start-1]<-threshold:start-=1
    cut=max(0,start-1);reason='Trước sụt lực Maxtest, lùi một mẫu bảo vệ'
    de=np.diff(e);prior=de[(tm[:-1]>=tm[start]-5)&(tm[:-1]<tm[start]-.5)]
    typical=np.median(np.abs(prior)) if len(prior) else .001
    local=np.flatnonzero((tm[:-1]>=tm[start]-.4)&(tm[:-1]<=tm[start]))
    jump=local[np.abs(de[local])>max(.03,10*typical)]
    if len(jump) and jump[0]<cut:cut=max(0,int(jump[0])-1);reason='Elong nhảy trước phản ứng sụt lực'
    return float(tm[cut]),reason

def process(sid,mp,tp,meta):
    header,mt=read_mt(mp);ter,bad=read_terminal(tp)
    f=ter.force_kg.to_numpy();tm=mt.Time.to_numpy();e=mt.Elong.to_numpy();notes=[];flags=[]
    r=dict(sample=sid,replicate=int(sid.split('_')[1]),**meta,L0_mm=L0,width_nominal_mm=WIDTH,thickness_nominal_mm=THICKNESS,area_nominal_mm2=AREA,
        Fmax_terminal_raw_kgf=float(f.max()),Fmax_terminal_raw_N=float(f.max()*G0),UTS_raw_MPa=float(f.max()*G0/AREA),
        maxtest_file=mp.relative_to(OUT).as_posix(),terminal_file=tp.relative_to(OUT).as_posix(),maxtest_n=len(mt),terminal_n=len(ter),malformed_terminal_n=len(bad),test_date_maxtest=header.get('TestDate'),mt_median_dt_s=float(np.median(np.diff(tm))),mt_max_gap_s=float(np.max(np.diff(tm))),source_header=header)
    base=pd.DataFrame(dict(sample=sid,terminal_record_index=np.arange(len(f)),terminal_source_line=ter.source_line,terminal_timestamp_raw=ter.timestamp_raw,force_terminal_raw_kgf=f,force_terminal_raw_N=f*G0,stress_raw_MPa=f*G0/AREA))
    med=median_filter(f,size=5,mode='nearest');spikes=(f-med)>np.maximum(20.,.2*np.maximum(med,1))
    if np.any(spikes):flags.append('FORCE_SPIKE_UNCONFIRMED');notes.append('Đỉnh lực thô bất thường vẫn giữ nguyên theo yêu cầu; không sửa hoặc loại khỏi UTS thô')
    base['force_spike_suspect']=spikes
    r['force_spike_n']=int(spikes.sum());r['force_peak_suspect']=bool(spikes[np.argmax(f)])
    if bad:notes.append(f'{len(bad)} dòng Terminal lỗi cú pháp được lưu riêng, không suy đoán số lực')
    if sid in ['G025_3','G025_4']:flags.append('EXTENSOMETER_OUTSIDE_BREAK');notes.append('Người dùng: vùng đứt nằm ngoài vùng đo Elong; giữ dữ liệu, hạn chế suy luận biến dạng đứt')
    elong_equals_disp=bool(np.allclose(e,mt.Disp.to_numpy(),atol=1e-8,rtol=0))
    if elong_equals_disp:
        flags.append('DISP_FALLBACK');notes.append('Elong trùng Disp toàn bộ; dùng Disp của máy làm chuyển vị thay thế theo quy ước đã chốt')
    try:
        tt,mapping=alignment(mt,ter);r.update(mapping)
        if mapping['sync_method'] in ['ONSET_ONLY_NO_SHARP_FRACTURE','ONSET_AND_RISING_FORCE_FALLBACK']:
            cut=float(tm[-1]);cutreason='Không có mốc gãy rõ; giữ vùng quan sát và đánh dấu cần kiểm tra'
            # If MT itself does have a sharp break, still remove its invalid postbreak Elong.
            if mapping['mt_drop_size']>=.1*np.quantile(mt.Load*1000/G0,.995):cut,cutreason=cutoff(mt,mapping)
        else:cut,cutreason=cutoff(mt,mapping)
        # Raw peak is retained. Curves end at 50 kg after the filtered peak, before post-break vibration.
        fs=median_filter(f,size=3,mode='nearest');peak_sync=int(np.flatnonzero(fs>=.9*np.quantile(fs,.995))[-1])
        below50=np.flatnonzero((np.arange(len(f))>peak_sync)&(fs<=50))
        ib50=int(below50[0]) if len(below50) else None
        below50_confirmed=bool(ib50 is not None and ib50+1<len(f) and fs[ib50+1]<=50)
        if ib50 is not None:
            cut=min(cut,float(np.nextafter(tt[ib50],-np.inf)))
            cutreason='Lực Terminal sau đỉnh giảm tới 50 kg; cắt trước rung động sau gãy'
        else:
            flags.append('NO_BELOW50');notes.append('Không thấy lực Terminal giảm tới 50 kg sau đỉnh; giữ mốc cắt đồng bộ sẵn có')
        if ib50 is not None and not below50_confirmed:flags.append('CUTOFF50_UNCONFIRMED')
        inds=np.flatnonzero((np.arange(len(f))>peak_sync)&(f<20))
        ib=int(inds[0]) if len(inds) else None
        if ib is None:flags.append('NO_BELOW20');notes.append('Không thấy lực dưới 20 kg sau đỉnh')
        else:cut=min(cut,float(np.nextafter(tt[ib],-np.inf)))
        confirmed=bool(ib is not None and ib+1<len(f) and f[ib+1]<20)
        if not confirmed:flags.append('BREAK_UNCONFIRMED')
        partial=mapping['partial_maxtest']
        same=elong_equals_disp
        if partial:flags.append('PARTIAL_MAXTEST');notes.append('Maxtest bắt đầu khi đã chịu tải, thiếu onset và zero extensometer; chỉ căn sụt lực để chẩn đoán')
        displacement_channel=mt.Disp.to_numpy() if same else e
        displacement_source='DISP_FALLBACK' if same else 'ELONG'
        zero=float(displacement_channel[mapping['mt_onset_index']]) if not partial else None
        raw=interp_safe(tt,tm,displacement_channel);ext=raw-zero if zero is not None else np.full(len(tt),np.nan)
        window=(tt>=mapping['mt_onset_s'])&(tt<=cut)&np.isfinite(raw)
        candidate=window & np.isfinite(ext)
        eps=ext/L0*100
        pre=(tm>=mapping['mt_onset_s'])&(tm<=cut)
        if zero is not None and not same:
            ep=e[pre]-zero;steps=np.diff(ep)
            if len(ep) and np.min(ep)<-.10:flags.append('ELONG_NEGATIVE');notes.append('Elong âm quá -0.10 mm trong vùng trước gãy')
            if np.any(steps<-.03) or np.any(np.abs(steps)>.15):flags.append('ELONG_JUMP');notes.append('Elong có bước giảm >0.03 mm hoặc nhảy >0.15 mm trước gãy')
            if len(ep)>10 and np.ptp(ep)<.02:flags.append('ELONG_FLAT');notes.append('Biên độ Elong quá nhỏ')
        if mapping['sync_method']=='ONSET_AND_RISING_FORCE_FALLBACK':flags.append('RISING_FORCE_FALLBACK');notes.append('Thiếu mốc gãy: fit tuyến tính qua onset và mốc tăng lực 10–60%, kiểm tra giữ lại 70–90%; không công nhận đồng bộ chắc chắn')
        if mapping['rmse_normalized'] is not None and (mapping['rmse_normalized']>.02 or mapping['max_landmark_residual_s']>1.5):flags.append('SYNC_REVIEW')
        if mapping['time_basis']=='TIMESTAMP_LOCAL_RECONSTRUCTION' and abs(mapping['time_scale']-1)>.05:flags.append('CLOCK_SCALE_REVIEW')
        if mapping['mt_drop_size']<.1*np.quantile(mt.Load*1000/G0,.995) or mapping['terminal_drop_size']<.1*np.quantile(f,.995):flags.append('WEAK_FRACTURE_ANCHOR')
        if r['mt_max_gap_s']>5*r['mt_median_dt_s']:flags.append('MT_TIME_GAP')
        if candidate.sum()<10:flags.append('TOO_FEW_CURVE_POINTS')
        # Warning about rupture outside the gauge does not invalidate the measured prepeak extension.
        blockers=[x for x in flags if x not in ['EXTENSOMETER_OUTSIDE_BREAK','DISP_FALLBACK','NO_BELOW50','CUTOFF50_UNCONFIRMED']]
        accepted=not blockers
        ip=int(np.argmax(f));eps_peak=float(eps[ip]) if candidate[ip] else None
        sens=[]
        for shift in [-.25,.25]:
            q=tt[ip]+shift;v=interp_safe(np.array([q]),tm,displacement_channel)[0]
            sens.append(float((v-zero)/L0*100) if zero is not None and mapping['mt_onset_s']<=q<=cut and np.isfinite(v) else None)
        r.update(last_valid_time_s=cut,cutoff_reason=cutreason,terminal_below20_index=ib,terminal_below20_confirmed=confirmed,terminal_below50_index=ib50,terminal_below50_confirmed=below50_confirmed,displacement_source=displacement_source,displacement_zero_mm=zero,elong_zero_mm=zero if not same else None,eps_UTS_candidate_pct=eps_peak,eps_UTS_QA_pct=eps_peak if accepted else None,eps_UTS_shift_minus025_pct=sens[0],eps_UTS_shift_plus025_pct=sens[1],eps_break_pct=None,accepted_strain=accepted,candidate_curve_points=int(candidate.sum()))
        base['time_maxtest_estimated_s']=tt;base['maxtest_displacement_interpolated_raw_mm']=raw;base['displacement_source']=displacement_source
        # Strict output displacement excludes postfracture and extrapolation. Audit raw remains separate.
        base['extension_mm']=np.where(candidate,ext,np.nan);base['strain_pct']=np.where(candidate,eps,np.nan)
        base['candidate_curve']=candidate;base['accepted_for_strain_analysis']=candidate & accepted
        base['status']=np.where(candidate,'QA_ACCEPTED' if accepted else 'REVIEW_REQUIRED',np.where(tt>cut,'AFTER_FRACTURE_CUTOFF','NO_VALID_EXTENSOMETER_OR_OUTSIDE_WINDOW'))
    except (ValueError,IndexError,ZeroDivisionError) as err:
        flags.append('SYNC_FAILED');notes.append(str(err));r.update(accepted_strain=False,candidate_curve_points=0,eps_UTS_candidate_pct=None,eps_UTS_QA_pct=None,eps_break_pct=None)
        for col in ['time_maxtest_estimated_s','maxtest_displacement_interpolated_raw_mm','extension_mm','strain_pct']:base[col]=np.nan
        base['displacement_source']='UNAVAILABLE'
        base['candidate_curve']=False;base['accepted_for_strain_analysis']=False;base['status']='SYNC_FAILED'
    r['quality_flags']=flags;r['notes']=notes;r['status']='QUA_KIEM_TRA_CO_DIEU_KIEN' if r['accepted_strain'] else 'CAN_KIEM_TRA'
    return r,base,mt,ter,bad

def clean_json(x):
    if isinstance(x,dict):return {k:clean_json(v) for k,v in x.items()}
    if isinstance(x,list):return [clean_json(v) for v in x]
    if isinstance(x,np.generic):return clean_json(x.item())
    if isinstance(x,float) and not np.isfinite(x):return None
    return x

def main():
    parser=argparse.ArgumentParser(description='Đồng bộ 420 mẫu Maxtest–Terminal')
    parser.add_argument('--samples',nargs='*',help='Chỉ chạy lại các mẫu đã chọn, ví dụ G001_1 G001_2')
    args=parser.parse_args()
    previous={r['sample']:r for r in json.loads((OUT/'analysis.json').read_text(encoding='utf-8'))['results']} if args.samples else {}
    meta=metadata();results=[]
    for sid,mp,tp in pairs():
        if args.samples and sid not in args.samples:
            results.append(previous[sid]);continue
        r,df,mt,ter,bad=process(sid,mp,tp,meta[sid.split('_')[0]])
        folder=OUT/r['group']/str(r['replicate']);folder.mkdir(parents=True,exist_ok=True)
        df.to_csv(folder/'Dong_bo_day_du.csv',index=False,encoding='utf-8-sig')
        df.loc[df.candidate_curve,['time_maxtest_estimated_s','force_terminal_raw_kgf','force_terminal_raw_N','displacement_source','extension_mm','stress_raw_MPa','strain_pct','accepted_for_strain_analysis','terminal_source_line']].to_csv(folder/'Luc_Chuyen_vi.csv',index=False,encoding='utf-8-sig')
        (folder/'Ket_qua.json').write_text(json.dumps(clean_json(r),ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
        (folder/'Dong_terminal_loi.json').write_text(json.dumps(bad,ensure_ascii=False,indent=2),encoding='utf-8')
        results.append(clean_json(r))
        if len(results)%25==0:print('Processed',len(results),flush=True)
    (OUT/'analysis.json').write_text(json.dumps(dict(results=results,metadata=meta),ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    rs=pd.DataFrame(results).drop(columns=['source_header','landmark_residual_s'],errors='ignore')
    rs['quality_flags']=['; '.join(r['quality_flags']) for r in results];rs['notes']=['; '.join(r['notes']) for r in results]
    rs.to_csv(OUT/'Tong_hop_420_mau.csv',index=False,encoding='utf-8-sig')
    gr=[]
    for group,sub in rs.groupby('group'):
        v=sub.UTS_raw_MPa.to_numpy();peak_review=int(sub.force_peak_suspect.sum())
        gr.append(dict(**meta[group],n=5,UTS_raw_mean_MPa=float(v.mean()),UTS_raw_sd_MPa=float(v.std(ddof=1)),UTS_raw_min_MPa=float(v.min()),UTS_raw_max_MPa=float(v.max()),UTS_raw_cv_pct=float(v.std(ddof=1)/v.mean()*100),n_strain_QA=int(sub.accepted_strain.sum()),n_force_peak_suspect=peak_review,group_status='Dinh luc tho can xac nhan' if peak_review else 'Du 5 dinh luc doc duoc'))
        sub.to_csv(OUT/group/'Tong_hop_5_mau.csv',index=False,encoding='utf-8-sig')
    pd.DataFrame(gr).to_csv(OUT/'Tong_hop_84_truong_hop.csv',index=False,encoding='utf-8-sig')
    (OUT/'groups.json').write_text(json.dumps(gr,ensure_ascii=False,indent=2),encoding='utf-8')
    from collections import Counter
    print('FLAGS',Counter(f for r in results for f in r['quality_flags']))
    print('ACCEPTED',sum(r['accepted_strain'] for r in results),'CURVES',sum(r['candidate_curve_points']>0 for r in results),flush=True)

if __name__=='__main__':main()
