import unittest,json,hashlib,tempfile
from pathlib import Path
import numpy as np,pandas as pd
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import processing as p

class Algorithms(unittest.TestCase):
    def test_parser_timestamp_date_and_force_only(self):
        text='Terminal log file\nDate: test\n---\n2026.08.05, 15:35:35.173, + 1.3 kg\n15:35:35.281, - 0.2 kg\n+ 5.50 kg\n15:35:35.501, + 117.+ 117.73 kg\n'
        with tempfile.TemporaryDirectory() as tmp:
            file=Path(tmp)/'a.log';file.write_text(text);d,b=p.read_terminal(file)
        self.assertEqual(d.force_kg.tolist(),[1.3,-.2,5.5]);self.assertEqual(len(b),1)
        self.assertEqual(d.source_line.tolist(),[4,5,6])
    def test_receipt_batches_preserve_order(self):
        d=pd.DataFrame(dict(clock_s=[1.,1.12,1.12,1.1,1.5,1.6],source_line=np.arange(4,10)))
        t,info=p.terminal_axis(d);self.assertTrue(np.all(np.diff(t)>0));self.assertEqual(info['timestamp_backwards_n'],1)
        self.assertAlmostEqual(t[-1],.6)
    def test_midnight(self):
        d=pd.DataFrame(dict(clock_s=[86399.8,86399.9,.02,.15],source_line=np.arange(4,8)))
        t,_=p.terminal_axis(d);np.testing.assert_allclose(t,[0,.1,.22,.35],atol=1e-9)
    def test_unknown_time_preserves_bad_line_positions(self):
        d=pd.DataFrame(dict(clock_s=[np.nan]*3,source_line=[4,5,7]))
        t,_=p.terminal_axis(d);np.testing.assert_array_equal(t,[0,1,3])
    def test_interpolation_no_extrapolation_or_long_gap(self):
        x=p.interp_safe(np.array([-.1,.04,.5,1.]),np.array([0,.04,.08,1.,1.04]),np.array([0,.1,.2,1.,1.1]))
        self.assertTrue(np.isnan(x[0]));self.assertTrue(np.isnan(x[2]));self.assertEqual(x[1],.1);self.assertEqual(x[3],1.)
    def test_known_mapping_and_spike_does_not_redefine_fracture(self):
        tm=np.arange(0,30,.04);ta=np.arange(0,31,.125);physical=ta-1.25
        def force(t):return np.where(t<1,0,np.where(t<25,(t-1)*5,np.where(t<25.2,(25.2-t)*600,0)))
        ft=force(physical);ft[100]=976.21
        mt=pd.DataFrame(dict(Time=tm,Load=force(tm)*p.G0/1000,Elong=tm*.02))
        ter=pd.DataFrame(dict(clock_s=ta+36000,source_line=np.arange(4,len(ta)+4),force_kg=ft))
        mapped,r=p.alignment(mt,ter)
        self.assertAlmostEqual(r['time_scale'],1,delta=.015);self.assertAlmostEqual(r['offset_s'],-1.25,delta=.2)
        self.assertGreater(r['terminal_drop_index'],180);self.assertEqual(ft.max(),976.21)

class DeliveredData(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        file=p.OUT/'analysis.json'
        if not file.exists():raise unittest.SkipTest('Outputs not generated yet')
        cls.rows=json.loads(file.read_text(encoding='utf-8'))['results']
    def test_all_pairs_and_factorial_conditions(self):
        self.assertEqual(len(list(p.pairs())),420);meta=p.metadata();self.assertEqual(len(meta),84)
        keys={(r['angle_deg'],r['layer_mm'],r['infill_pct'],r['pattern']) for r in meta.values()}
        self.assertEqual(len(keys),84);self.assertEqual(len({r['sample'] for r in self.rows}),420)
    def test_every_raw_force_and_peak_unchanged(self):
        for r in self.rows:
            t,_=p.read_terminal(p.OUT/r['terminal_file']);d=pd.read_csv(p.OUT/r['group']/str(r['replicate'])/'Dong_bo_day_du.csv')
            np.testing.assert_allclose(t.force_kg,d.force_terminal_raw_kgf,rtol=0,atol=1e-12)
            self.assertEqual(r['Fmax_terminal_raw_kgf'],float(t.force_kg.max()))
            self.assertAlmostEqual(r['UTS_raw_MPa'],t.force_kg.max()*p.G0/40,places=9)
    def test_valid_window_and_units_for_all(self):
        for r in self.rows:
            d=pd.read_csv(p.OUT/r['group']/str(r['replicate'])/'Dong_bo_day_du.csv');c=d[d.candidate_curve]
            np.testing.assert_allclose(d.stress_raw_MPa,d.force_terminal_raw_N/40)
            np.testing.assert_allclose(c.strain_pct,c.extension_mm/50*100)
            self.assertTrue(d.loc[~d.candidate_curve,'extension_mm'].isna().all())
            if len(c):self.assertTrue((c.time_maxtest_estimated_s<=r['last_valid_time_s']+1e-8).all())
    def test_unconfirmed_spike_retained_and_flagged(self):
        r=next(r for r in self.rows if r['sample']=='G037_1')
        self.assertEqual(r['Fmax_terminal_raw_kgf'],976.21);self.assertTrue(r['force_peak_suspect']);self.assertFalse(r['accepted_strain'])
    def test_displacement_fallback_and_truncated_source_status(self):
        for r in self.rows:
            if r['sample']=='G009_1':
                self.assertFalse(r['accepted_strain']);self.assertIsNone(r['eps_UTS_QA_pct'])
            if 'DISP_FALLBACK' in r['quality_flags']:
                self.assertEqual(r['displacement_source'],'DISP_FALLBACK')
                self.assertGreater(r['candidate_curve_points'],0)
    def test_source_sha256_preserved(self):
        files=json.loads((p.OUT/'source_manifest.json').read_text(encoding='utf-8'))
        self.assertEqual(len(files),841)
        for f in files:self.assertEqual(hashlib.sha256((p.OUT/f['path']).read_bytes()).hexdigest(),f['sha256'])
    def test_all_groups_keep_five_raw_peaks(self):
        groups=json.loads((p.OUT/'groups.json').read_text(encoding='utf-8'))
        for g in groups:
            v=[r['UTS_raw_MPa'] for r in self.rows if r['group']==g['group']]
            self.assertEqual(len(v),5);self.assertAlmostEqual(np.mean(v),g['UTS_raw_mean_MPa'],places=10)

if __name__=='__main__':unittest.main(verbosity=2)
