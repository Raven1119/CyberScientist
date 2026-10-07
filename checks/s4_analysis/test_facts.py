from .facts import steady_then_higher


def test_negative_and_missing_display_sentinels_do_not_count_as_failed_patterns():
    assert steady_then_higher(-1,100,3) is None
    assert steady_then_higher(None,100,3) is None
    assert steady_then_higher(50,None,3) is None
    assert steady_then_higher(50,90,2) is True
    assert steady_then_higher(0,100,2) is False
    assert steady_then_higher(50,90,1) is False
