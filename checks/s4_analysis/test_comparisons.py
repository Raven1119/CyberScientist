from .comparisons import jaccard,package_name,reliability


def test_unknown_hashes_and_standard_library_do_not_become_environment_gaps():
    assert jaccard([],['a']) is None and jaccard(['a'],['a','b'])==.5
    assert package_name('json') is None and package_name('os.path') is None
    assert package_name('sklearn.cluster')=='scikit-learn'


def test_reliability_requires_positive_sample_floor_and_both_rates():
    assert reliability(2,0,0,2)==(1,1,'unknown_or_unusable')
    assert reliability(5,0,0,5)==(1,1,'conditionally_reliable')
    assert reliability(9,1,4,13)[2]=='unknown_or_unusable'
    assert reliability(0,0,0,0)==(None,None,'unknown_or_unusable')
