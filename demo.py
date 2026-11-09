import json

from headline_matcher import AliasIndex, extract, mask_headline

aliases = [
    {'alias': 'Northbridge Research', 'evidence_id': 'broker:1'},
    {'alias': 'Example Robotics', 'evidence_id': 'issuer:1'},
    {'alias': 'Harbor Devices', 'evidence_id': 'issuer:2'},
]
broker_ids = {'broker:1'}
index = AliasIndex(aliases)

examples = [
    ('Northbridge Research initiates coverage of Example Robotics', 'analyst_action'),
    ('Example Robotics downgraded by Northbridge Research', 'analyst_action'),
    ('Northbridge Research upgrades Example Robotics and Harbor Devices', 'analyst_action'),
    ('Example Robotics reports EPS above consensus', 'earnings_estimate_comparison'),
    ('Example Robotics to report earnings', 'earnings_preview'),
    ('Example Robotics raises full-year guidance', 'guidance_change'),
    ('Example Robotics declares a dividend', 'capital_return'),
    ('Example Robotics acquires Harbor Devices', 'acquisition'),
]

for number, (headline, expected) in enumerate(examples, 1):
    result = extract({'news_id': str(number), 'headline': headline}, index, broker_ids)
    assert expected in {event['frame'] for event in result['events']}
    result['masked_headline'] = mask_headline(headline, result['headline_mentions'], broker_ids)
    print(json.dumps(result, ensure_ascii=False))

for headline in (
    'Northbridge Research upgrades Example Robotics - Reuters',
    'Northbridge Research double-downgrades Harbor Devices',
    'Northbridge Research resumes coverage of Harbor Devices',
):
    assert extract({'news_id': 'new', 'headline': headline}, index, broker_ids)['events'][0]['frame'] == 'analyst_action'

headline = 'Northbridge Research upgrades Example Robotics software; stock jumps'
assert not extract({'news_id': 'negative', 'headline': headline}, index, broker_ids)['events']

for headline, field, values in (
    ('Northbridge Research cuts its target on Harbor Devices to $42 from $50',
     'price_target', {'old': '$50', 'new': '$42'}),
    ('Northbridge Research upgrades Harbor Devices from Hold to Buy',
     'rating', {'old': 'Hold', 'new': 'Buy'}),
    ('Example Robotics Q3 adjusted EPS $1.12 vs. $1.04 est.', 'comparisons',
     [{'basis': 'adjusted', 'metric': 'EPS', 'actual': '$1.12',
       'consensus': '$1.04', 'fiscal_period': 'Q3'}]),
):
    event = extract({'news_id': 'structured', 'headline': headline}, index, broker_ids)['events'][0]
    assert event[field] == values, event
