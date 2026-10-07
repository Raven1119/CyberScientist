from . import collect
from .tables import attempt_row, number, timestamp, write_csv

import pytest


def test_nullable_scores_and_round_boundaries_stay_distinct():
    a={'id':7,'authorId':'a','challengeId':'c','createdAt':'2026-08-01T00:00:00Z',
       'score':0,'scorecard':{'harbor_score':100,'trace_score':0},
       'scoringState':{'scoreIsFinal':False}}
    topic={'id':'c','roundStartAt':'2026-07-31T00:00:00Z','roundEndAt':'2026-08-01T00:00:00Z'}
    r=attempt_row(a,topic,{'a':'verified_local_source'})
    assert r['display_score']==0 and r['science_score']==100 and r['trace_score']==0
    assert r['is_within_round'] is False and r['minutes_since_round_start']==1440
    assert r['score_is_final'] is False and r['ours'] is True
    r=attempt_row({'id':8,'authorId':'b'},topic,{})
    assert r['display_score'] is None and r['trace_score'] is None and r['is_within_round'] is None


def test_zero_score_is_collected_and_does_not_mean_missing():
    assert collect.has_score({'score':0})
    assert collect.has_score({'scorecard':{'trace_score':0}})
    assert collect.has_score({'scoringState':{'displayScore':0}})
    assert collect.has_score({'resultsJson':{'harbor_score':0}})
    assert not collect.has_score({'scorecard':None,'resultsJson':None})
    assert number(False) is None and number('nan') is None


def test_pagination_reads_all_pages_and_excludes_only_explicit_drafts(tmp_path,monkeypatch):
    class Client:
        root=tmp_path
        def get(self,path):
            if '/attempts?' not in path:return {'id':'c'}
            rows=[{'id':1,'challengeId':'c','status':'submitted'},
                  {'id':2,'challengeId':'c','status':'draft'}] if 'page=1&' in path else [
                  {'id':3,'challengeId':'c','status':'submitted'}]
            return {'attempts':rows,'total':3,'totalNonDraft':2}
    monkeypatch.setattr(collect,'observed',lambda *_:'2026-08-01T00:00:00+00:00')
    topic,rows,pages=collect.collect_topic(Client(),'c',1)
    assert [r['id'] for r in rows]==[1,3] and len(pages)==2
    assert topic['_round_seq_from_season']==1


def test_repeating_page_cannot_silently_count_as_full_coverage(tmp_path,monkeypatch):
    class Client:
        root=tmp_path
        def get(self,path):
            if '/attempts?' not in path:return {'id':'c'}
            return {'attempts':[{'id':1,'challengeId':'c'}],'total':100}
    monkeypatch.setattr(collect,'observed',lambda *_:'2026-08-01T00:00:00+00:00')
    with pytest.raises(ValueError,match='without progress'):
        collect.collect_topic(Client(),'c',1)


def test_early_empty_page_is_incomplete_and_preserves_partial_rows(tmp_path,monkeypatch):
    class Client:
        root=tmp_path
        def get(self,path):
            if '/attempts?' not in path:return {'id':'c'}
            return {'attempts':[{'id':1,'challengeId':'c'}] if 'page=1&' in path else [],'total':100}
    monkeypatch.setattr(collect,'observed',lambda *_:'2026-08-01T00:00:00+00:00')
    with pytest.raises(collect.IncompleteTopic,match='before declared total') as caught:
        collect.collect_topic(Client(),'c',1)
    assert len(caught.value.attempts)==1 and len(caught.value.pages)==2


def test_large_table_parquet_keeps_unknown_and_zero_distinct(tmp_path):
    import sys
    from pathlib import Path
    sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'.package-checks/s4_analysis/deps'))
    duckdb=pytest.importorskip('duckdb')
    source=tmp_path/'values.csv'
    target=write_csv(source,[{'id':1,'score':None,'name':'测试'},{'id':2,'score':0,'name':'quoted, value'}],csv_limit=1)
    assert target.suffix=='.parquet' and not source.exists()
    with duckdb.connect() as connection:
        rows=connection.execute('SELECT id,score,name FROM read_parquet(?) ORDER BY id',[str(target)]).fetchall()
    assert rows==[('1',None,'测试'),('2','0','quoted, value')]


def test_csv_preserves_null_zero_and_utf8(tmp_path):
    import csv
    p=tmp_path/'values.csv'
    write_csv(p,[{'id':1,'score':None,'name':'测试'},{'id':2,'score':0,'name':'quoted, value'}])
    with p.open() as f: rows=list(csv.DictReader(f))
    assert rows[0]['score']=='' and rows[1]['score']=='0' and rows[0]['name']=='测试'


def test_naive_or_invalid_timestamps_are_unknown():
    assert timestamp('2026-08-01T00:00:00') is None
    assert timestamp('not a date') is None
