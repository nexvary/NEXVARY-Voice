import json
import time
from voice_engine.asset_inventory import voice_map,functional_report


def test_voice_discovery_and_partial_mapping_preserves_extra_language(tmp_path,monkeypatch):
    monkeypatch.delenv('NEXVARY_PIPER_VOICES',raising=False)
    folder=tmp_path/'models'/'voices'/'ar';folder.mkdir(parents=True)
    model=folder/'ar_JO-kareem-medium.onnx';model.write_bytes(b'x'*2000)
    (folder/(model.name+'.json')).write_text(json.dumps({'language':{'code':'ar_JO'},'audio':{'sample_rate':22050},'phoneme_id_map':{'a':[1]}}))
    (tmp_path/'voices.json').write_text(json.dumps({'fr':'existing-french.onnx'}))
    mapping=voice_map(tmp_path)
    assert mapping['ar']==str(model.resolve())
    assert mapping['fr']=='existing-french.onnx'


def test_modified_model_invalidates_historical_functional_success(tmp_path,monkeypatch):
    monkeypatch.delenv('NEXVARY_PIPER_VOICES',raising=False)
    model=tmp_path/'voice.onnx';model.write_bytes(b'x')
    (tmp_path/'voices.json').write_text(json.dumps({'en':str(model)}))
    (tmp_path/'functional-tests.json').write_text(json.dumps({'voices':{'passed':True,'checked_at':time.time()-10}}))
    assert not functional_report(tmp_path)['voices']['current_assets_unchanged']


def test_changing_whisper_quality_invalidates_old_recognition_test(tmp_path):
    (tmp_path/'functional-tests.json').write_text(json.dumps({'whisper':{'passed':True,'checked_at':time.time(),'data':{'model':'base'}}}))
    assert functional_report(tmp_path)['whisper']['current_assets_unchanged']
    (tmp_path/'preferences.json').write_text(json.dumps({'whisper_model':'small'}))
    assert not functional_report(tmp_path)['whisper']['current_assets_unchanged']
