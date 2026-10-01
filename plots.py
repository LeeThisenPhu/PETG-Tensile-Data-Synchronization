from pathlib import Path
import json,sys,argparse
import numpy as np,pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from PIL import Image,ImageOps,ImageDraw
import processing as p
OUT=p.OUT
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False})
COLORS=['#287ca1','#df8b2c','#47955c','#aa578e','#7963b0']

def curve(ax,r,df,label=None):
    x=df.strain_pct.copy();y=df.stress_raw_MPa.copy();y[~df.candidate_curve]=np.nan
    color=COLORS[r['replicate']-1]
    if df.candidate_curve.any():
        ax.plot(x,y,color=color,lw=1.2,ls='-' if r['accepted_strain'] else '--',label=label)
    else:ax.plot([],[],color=color,ls=':',label=label or f"Mẫu {r['replicate']}: không có ε hợp lệ")
    ax.grid(alpha=.2);ax.set_xlabel('Biến dạng kỹ thuật ε (%)');ax.set_ylabel('Ứng suất danh nghĩa σ (MPa)')

def title(r):return f"{r['group']} · {r['angle_deg']}° · lớp {r['layer_mm']} mm · infill {r['infill_pct']}% · {r['pattern']}"

def sample_plot(r):
    folder=OUT/r['group']/str(r['replicate']);df=pd.read_csv(folder/'Dong_bo_day_du.csv')
    fig,ax=plt.subplots(figsize=(8.5,5.7));curve(ax,r,df)
    source='Elong Maxtest' if r.get('displacement_source')=='ELONG' else 'Disp Maxtest thay Elong'
    ax.set_title(f"{r['sample']} — lực Terminal / {source}\nA₀ = 40 mm²; L₀ = 50 mm; tốc độ thử 2 mm/min",fontsize=12)
    if df.candidate_curve.any():
        ax.axhline(r['UTS_raw_MPa'],color='#888',ls=':',lw=.8,label=f"UTS thô = {r['UTS_raw_MPa']:.2f} MPa")
        ax.legend(fontsize=9)
    else:
        ax.text(.5,.55,'KHÔNG ĐỦ ELONG / ĐỒNG BỘ ĐỂ DỰNG ĐƯỜNG ε\nXem dữ liệu thô và biểu đồ kiểm tra',ha='center',va='center',transform=ax.transAxes,color='#a03b35',fontsize=11)
    footer=f"Chuyển vị: {source}. Đường kết thúc khi lực Terminal sau đỉnh giảm đến 50 kg."
    fig.text(.5,.025,footer,ha='center',fontsize=8.4,color='#555' if r['accepted_strain'] else '#a03b35')
    fig.tight_layout(rect=(0,.06,1,1));fig.savefig(folder/'Ung_suat_Bien_dang.png',dpi=150);fig.savefig(folder/'Ung_suat_Bien_dang.svg');plt.close(fig)
    h,mt=p.read_mt(OUT/r['maxtest_file']);ter,_=p.read_terminal(OUT/r['terminal_file'])
    fig,axes=plt.subplots(3,1,figsize=(9,8.5));tm=mt.Time.to_numpy();fm=mt.Load.to_numpy();ft=ter.force_kg.to_numpy()
    fmn,_,_=p.norm(fm);ftn,_,_=p.norm(ft);tt=df.time_maxtest_estimated_s.to_numpy()
    axes[0].plot(tm,fmn,color='#287ca1',label='Maxtest Load, chỉ căn thời gian',lw=1)
    if np.isfinite(tt).any():axes[0].plot(tt,ftn,color='#df8b2c',label='Terminal sau đồng bộ',lw=.8,alpha=.8)
    axes[0].set_ylabel('Lực chuẩn hóa');axes[0].legend(fontsize=8)
    rm=r.get('rmse_normalized');res=r.get('max_landmark_residual_s')
    diagnostic=f"RMSE={100*rm:.2f}%; lệch mốc giữa max={res:.2f}s" if rm is not None else 'Không đủ mốc kiểm chứng đồng bộ'
    axes[0].set_title(f"{r['sample']} — {diagnostic}\n{r.get('time_basis','SYNC_FAILED')}",fontsize=11)
    channel=mt.Elong if r.get('displacement_source')!='DISP_FALLBACK' else mt.Disp
    label='Elong Maxtest nguyên bản' if r.get('displacement_source')!='DISP_FALLBACK' else 'Disp Maxtest dùng thay Elong'
    axes[1].plot(tm,channel,color='#47955c',lw=.9,label=label)
    cut=r.get('last_valid_time_s')
    if cut is not None:
        axes[1].axvline(cut,color='black',ls='--',label='Cắt tại 50 kg sau đỉnh');axes[1].axvspan(max(tm[0],cut),tm[-1],color='#efb3b3',alpha=.35)
    axes[1].set_ylabel('Chuyển vị (mm)');axes[1].legend(fontsize=8)
    axes[2].plot(df.terminal_source_line,ft,color='#7963b0',lw=.9)
    bad=df.force_spike_suspect
    if bad.any():axes[2].scatter(df.loc[bad,'terminal_source_line'],ft[bad],color='red',s=25,label='Điểm lực nghi vấn: giữ nguyên');axes[2].legend(fontsize=8)
    axes[2].set(xlabel='Số dòng Terminal gốc',ylabel='Lực Terminal thô (kgf)')
    for ax in axes:ax.grid(alpha=.2)
    axes[1].set_xlabel('Thời gian Maxtest (s)')
    fig.tight_layout();fig.savefig(folder/'Kiem_tra_dong_bo.png',dpi=120);plt.close(fig)
    return df

def group_plot(rs,dfs):
    g=rs[0]['group'];folder=OUT/g
    # Whole range is retained even where an unconfirmed raw force spike expands the axis.
    fig,ax=plt.subplots(figsize=(10,6.5))
    for r,d in zip(rs,dfs):
        state='' if r['accepted_strain'] else ' [kiểm tra]'
        if not d.candidate_curve.any():state=' [không có ε hợp lệ]'
        curve(ax,r,d,label=f"Mẫu {r['replicate']}{state}")
    ax.set_title(title(rs[0]),fontsize=13);ax.legend(fontsize=9)
    fig.text(.5,.018,'Nét liền: qua kiểm tra có điều kiện. Nét đứt: chỉ quan sát, cần xem QA.',ha='center',fontsize=9)
    fig.tight_layout(rect=(0,.045,1,1));fig.savefig(folder/'So_sanh_5_mau.png',dpi=165);fig.savefig(folder/'So_sanh_5_mau.svg');plt.close(fig)
    fig,axes=plt.subplots(2,3,figsize=(12,7.5))
    for ax,r,d in zip(axes.flat,rs,dfs):
        curve(ax,r,d);ax.set_title(r['sample']+('' if r['accepted_strain'] else ' [kiểm tra]'),fontsize=10)
        if not d.candidate_curve.any():ax.text(.5,.5,'Không đủ ε hợp lệ',transform=ax.transAxes,ha='center',color='#a03b35')
        ax.tick_params(labelsize=8);ax.xaxis.label.set_size(8);ax.yaxis.label.set_size(8)
    axes.flat[-1].axis('off');axes.flat[-1].text(.03,.9,'UTS thô (MPa)\n\n'+'\n'.join(f"Mẫu {r['replicate']}: {r['UTS_raw_MPa']:.3f}"+(' *' if r['force_peak_suspect'] else '') for r in rs)+'\n\n* Đỉnh lực cần xác nhận',va='top',fontsize=11)
    fig.suptitle(title(rs[0]),fontsize=13);fig.tight_layout(rect=(0,0,1,.96));fig.savefig(folder/'Tung_mau_trong_nhom.png',dpi=130);plt.close(fig)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--start',type=int,default=1);ap.add_argument('--end',type=int,default=84);args=ap.parse_args()
    rows=json.loads((OUT/'analysis.json').read_text(encoding='utf-8'))['results']
    for gn in range(args.start,args.end+1):
        rs=[r for r in rows if r['group']==f'G{gn:03}'];dfs=[sample_plot(r) for r in rs];group_plot(rs,dfs)
        print('Charts',f'G{gn:03}',flush=True)
    if args.start==1 and args.end==84:
        folder=OUT/'Kiem_tra_tong_quan';folder.mkdir(exist_ok=True)
        for start in range(1,85,12):
            sheet=Image.new('RGB',(1440,4*340),'white');draw=ImageDraw.Draw(sheet)
            for k,gn in enumerate(range(start,min(start+12,85))):
                im=Image.open(OUT/f'G{gn:03}'/'So_sanh_5_mau.png').convert('RGB');im.thumbnail((480,320))
                x=(k%3)*480;y=(k//3)*340;sheet.paste(im,(x,y));draw.text((x+15,y+318),f'G{gn:03}',fill='black')
            sheet.save(folder/f'G{start:03}_G{min(start+11,84):03}.jpg',quality=90)
if __name__=='__main__':main()
