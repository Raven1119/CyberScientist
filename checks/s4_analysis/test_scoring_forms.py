from .scoring_forms import evidence_checks


def test_heading_names_can_resolve_exact_source_without_inventing_a_quote():
    output={'metrics':[{'evidence':{'field':'How you are scored','quote':'A score of 100'}}]}
    result=evidence_checks(output,{'content':'Details. A score of 100 requires a certificate.'})
    assert result[0]['exact_quote_valid'] and not result[0]['declared_field_exact']
    assert result[0]['resolved_source_fields']==['content']
    output['metrics'][0]['evidence']['quote']='A score of 99'
    assert not evidence_checks(output,{'content':'A score of 100'})[0]['exact_quote_valid']
