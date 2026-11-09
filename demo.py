import json

from headline_matcher import AliasIndex, extract, mask_headline, name_aliases

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

def check_aliases_and_apostrophes():
    index = AliasIndex([
        {'alias': alias, 'evidence_id': 'auto'}
        for alias in (*name_aliases("O'Reilly Automotive Inc."), "O'Reilly Auto Parts")
    ] + [
        {'alias': 'Harbor Devices', 'evidence_id': 'devices'},
        {'alias': 'Harbor Devices Holdings', 'evidence_id': 'holdings'},
        {'alias': 'Harbor Devices Holdings', 'evidence_id': 'collision'},
        {'alias': "Fisher's Capital Research", 'evidence_id': 'broker'},
    ])
    brokers = {'broker'}
    for headline, issuer in (
        ("Fisher’s Capital Research upgrades O'Reilly Auto Parts", "O'Reilly Auto Parts"),
        ("Fisher's Capital Research downgrades ‘O’Reilly Automotive’", 'O’Reilly Automotive'),
        ("O’Reilly Automotive Inc.’s shares downgraded by Fisher's Capital Research", None),
        ("O’Reilly Automotive’s EPS $1.12 vs. $1.04 est.", None),
    ):
        result = extract({'news_id': 'alias', 'headline': headline}, index, brokers)
        mentions = result['headline_mentions']
        assert any(row['evidence_ids'] == ('auto',) for row in mentions), result
        for row in mentions:
            assert headline[row['start']:row['end']] == row['text']
        if issuer:
            roles = result['events'][0]['roles']
            assert [(row['role'], row['text']) for row in roles] == [
                ('broker', mentions[0]['text']), ('affected_issuer', issuer)
            ], roles
        if 'shares downgraded' in headline:
            assert [role['role'] for role in result['events'][0]['roles']] == ['broker', 'affected_issuer']
        if 'EPS' in headline:
            assert result['events'][0]['comparisons'][0]['consensus'] == '$1.04', result

    headline = 'Harbor Devices Holdings and Harbor Devices'
    mentions = extract({'news_id': 'collision', 'headline': headline}, index, brokers)['headline_mentions']
    assert [(row['text'], row['evidence_ids']) for row in mentions] == [
        ('Harbor Devices Holdings', ('collision', 'holdings')),
        ('Harbor Devices', ('devices',)),
    ]


check_aliases_and_apostrophes()

assert 'Aena' in name_aliases('Aena, S.M.E., S.A.')
assert 'Eurogroup Laminations' in name_aliases('Eurogroup Laminations S.p.A.')
international = AliasIndex([
    {'alias': 'Meliá Hotels', 'evidence_id': 'hotel'},
    {'alias': 'Marks & Spencer', 'evidence_id': 'retail'},
])
international_headline = 'Melia\u0301 Hotels and Marks and Spencer'
assert [international_headline[span.start:span.end] for span in international.find(international_headline)] == [
    'Melia\u0301 Hotels', 'Marks and Spencer',
]
