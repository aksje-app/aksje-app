import io, zipfile, json
from unittest.mock import patch
from superfund_diagnostics import diagnostic_zip

def test_rotation_evidence_present_in_diagnostic_zip():
    snapshot={'at':'2026-10-14T12:00:00Z','model':{'positions':{},'cash':0},
              'rotation_shadow':{'mode':'SHADOW_ONLY','review_count':1,'candidates':[]},
              'rotation_comparison':{'mode':'SHADOW_ONLY','measured_count':1,'pairs':{}},
              'challenger_report':{'totals':{'evaluated':5},'rows':[]}}
    read_calls=[]
    def fake_read(name,default=None):
        read_calls.append(name)
        if name=='snapshot.json':return snapshot
        return {} if default is None else default
    with patch('superfund_runtime.read',side_effect=fake_read),patch('superfund_runtime.config',return_value={}):
        data,_=diagnostic_zip()
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for name in ('rotation_controls.json','rotation_shadow.json','rotation_comparison.json','challenger_report.json'):
            assert name in z.namelist()
        assert json.loads(z.read('rotation_controls.json'))['trade_execution_enabled'] is False
        timeline=json.loads(z.read('decision_timeline.json'))
        assert timeline['snapshot_at']=='2026-10-14T12:00:00Z'
        assert timeline['evidence_type']=='SAVED_SNAPSHOT_ONLY'
        assert timeline['shadow_names']==[]
        assert timeline['timestamp_quality']['snapshot_at_present'] is True
        assert timeline['timestamp_quality']['paired_start_present'] is False
        assert timeline['shadow_records_present'] is False
        assert timeline['learning_records_present'] is False
        assert timeline['rotation_observations'] == 1
        assert timeline['rotation_measured_pairs'] == 1
    assert read_calls.count('snapshot.json') == 1
    assert 'decision_timeline.json' not in read_calls
