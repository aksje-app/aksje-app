from evidence_integrity import finalize_run_integrity
from market_intelligence import combined_quality_summary


def _candidate(ticker='AAA.OL', insider_status='CHECKED_NO_EVENTS', source_type='OFFICIAL_EXCHANGE_FEED'):
    return {
        'ticker': ticker,
        'valid_for_decision': True,
        'confidence_score': 85,
        'raw': {
            'insider_intelligence': {
                'coverage': insider_status,
                'search_log': [{
                    'source': 'Official exchange',
                    'source_type': source_type,
                    'attempted': True,
                    'status': 'SUCCESS_NO_RESULTS',
                    'direct_primary_source_checked': True,
                }],
            },
            'news_intelligence': {'coverage': 'VERIFIED_FACTS_FOUND', 'events': [{'title': 'Fact'}]},
        },
        'evidence_coverage': {
            'insider': {'status': insider_status},
            'news': {'status': 'VERIFIED_FACTS_FOUND'},
        },
    }


def test_official_exchange_primary_check_does_not_create_false_gap():
    run = {'run_id': 'RC1', 'candidates': [_candidate()], 'raw_top3': [_candidate()], 'warnings': []}
    finalize_run_integrity(run)
    assert run['report_status']['critical_gaps'] == []
    assert run['warnings'] == []


def test_real_critical_gap_is_machine_readable_warning():
    c = _candidate(insider_status='NOT_SEARCHED', source_type='SECONDARY_STRUCTURED')
    c['raw']['insider_intelligence']['search_log'][0]['direct_primary_source_checked'] = False
    run = {'run_id': 'RC1', 'candidates': [c], 'raw_top3': [c], 'warnings': []}
    finalize_run_integrity(run)
    assert run['report_status']['critical_gaps']
    assert any('AAA.OL/insider' in warning for warning in run['warnings'])


def test_partial_quality_uses_automatic_revalidation_language():
    summary = combined_quality_summary(
        [{'valid_for_decision': True, 'evidence_valid_for_decision': True},
         {'valid_for_decision': True, 'evidence_valid_for_decision': False}],
        {'valid_for_decision': 2},
        {'verified_facts': 1, 'manual_review_required': 1, 'sources_attempted': 2},
    )
    assert summary['status'] == 'DELVIS – AUTOMATISK REVALIDERING PÅKREVD'
