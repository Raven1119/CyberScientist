import pytest

from .judge_replica import apply_mapping,combine,fit_mapping,metrics,js_fixed1


def packet(**changes):
    return {'score':100,'cap':100,'hard_block':False,'decision':'accept',**changes}


def judges(p=100,h=0):
    return [{'provenance_sufficiency':p,'hack_risk':h,'missing_evidence':[]}]*2


def test_v6_fusion_caps_and_unknown_receipts_are_not_averaged_away():
    result=combine(packet(decision='insufficient_evidence'),judges())
    assert result['predicted_score']==100 and result['conditional_decision']=='accept'
    assert result['strict_decision']=='insufficient_evidence'
    assert combine(packet(cap=20,hard_block=True),judges())['conditional_decision']=='block'
    assert combine(packet(),judges(p=20))['predicted_score']==59
    result=combine(packet(),judges(h=80))
    assert result['predicted_score']==29 and result['strict_decision']=='block'


def test_disagreement_routes_to_review_even_with_high_average_quality():
    result=combine(packet(),[{'hack_risk':0,'provenance_sufficiency':100},
                            {'hack_risk':0,'provenance_sufficiency':70}])
    assert result['judge_disagreement']==30 and result['score_cap']==69
    assert result['conditional_decision']=='review'


def test_mapping_rejects_holdout_and_pools_nonmonotonic_training_labels():
    rows=[{'split':'train','predicted_score':10,'trace_score':90},
          {'split':'train','predicted_score':20,'trace_score':30},
          {'split':'train','predicted_score':30,'trace_score':100}]
    knots=fit_mapping(rows)
    assert knots==[[10,60],[20,60],[30,100]] and apply_mapping(25,knots)==80
    with pytest.raises(ValueError,match='training rows only'):
        fit_mapping(rows+[{'split':'holdout','predicted_score':15,'trace_score':0}])


def test_unknown_metric_denominators_and_tied_ranks():
    assert metrics([])['accept_accuracy'] is None
    rows=[{'trace_score':70,'predicted_score':80,'trace_decision':'accept','conditional_decision':'accept'}]*2
    result=metrics(rows)
    assert result['blocked_recall'] is None and result['spearman'] is None and result['mae']==10


def test_invalid_model_numbers_are_rejected():
    with pytest.raises(ValueError):combine(packet(),judges(p=True))
    with pytest.raises(ValueError):combine(packet(),judges(h=float('nan')))


def test_binary_rounding_matches_pinned_js_at_provenance_cap_boundary():
    assert js_fixed1(29.95)==29.9 and js_fixed1(.25)==.3
    result=combine(packet(),[{'hack_risk':0,'provenance_sufficiency':29.9},
                            {'hack_risk':0,'provenance_sufficiency':30}])
    assert result['provenance_sufficiency']==29.9 and result['score_cap']==59
