"""Deterministic financial headline and wire-lead candidate extraction."""

from dataclasses import dataclass
from datetime import date
import re
import unicodedata

PUBLISHER_SUFFIX = re.compile(
    r'\s+[|–—-]\s+(?:the new york times|new york times|thomson reuters|reuters)\s*$',
    re.I,
)
TOKEN = re.compile(r'[^\W_]+')
SUFFIXES = {'inc', 'incorporated', 'corp', 'corporation', 'ltd', 'limited',
            'plc', 'llc', 'company', 'co'}
RULE_VERSION = 'issuer-frame-v7'


def tokenize(text):
    return [(unicodedata.normalize('NFKC', token[0]).casefold(), token.start(), token.end())
            for token in TOKEN.finditer(text)]


@dataclass(frozen=True)
class Span:
    start: int
    end: int
    evidence_ids: tuple


class AliasIndex:
    """A token trie that retains collisions and prefers the longest span."""

    def __init__(self, rows):
        self.trie = {}
        for row in rows:
            words = tuple(token for token, _, _ in tokenize(row['alias']))
            if not words or len(words) > 16 or sum(map(len, words)) < 3:
                continue
            if len(words) == 1 and not row.get('allow_single_token'):
                continue
            node = self.trie
            for word in words:
                node = node.setdefault(word, {})
            node.setdefault(None, set()).add(row['evidence_id'])

    def find(self, text):
        words = tokenize(text)
        spans = []
        index = 0
        while index < len(words):
            # A one-letter token inside dotted initials cannot start an issuer name.
            if index and len(words[index][0]) == 1 and len(words[index - 1][0]) == 1:
                if text[words[index - 1][2]:words[index][1]] == '.':
                    index += 1
                    continue
            node = self.trie
            longest = None
            for end in range(index, min(index + 16, len(words))):
                node = node.get(words[end][0])
                if not node:
                    break
                if None in node:
                    longest = end, tuple(sorted(node[None]))
            if longest is None:
                index += 1
                continue
            end, evidence = longest
            spans.append(Span(words[index][1], words[end][2], evidence))
            index = end + 1
        return spans


def name_aliases(name):
    """Return conservative legal-name and suffix-stripped candidates."""
    name = re.split(r'\s+(?:class [a-z0-9-]+\s+)?'
                    r'(?:common (?:stock|shares)|ordinary shares|capital stock)\b',
                    name, maxsplit=1, flags=re.I)[0].strip()
    tokens = tokenize(name)
    if not tokens:
        return set()
    aliases = {name}
    while len(tokens) > 2 and tokens[-1][0] in SUFFIXES:
        tokens.pop()
    aliases.add(name[:tokens[-1][2]])
    return aliases


ACQUIRES = re.compile(
    r"\s*[,:(]?\s*(?:(?:has |will |is |would )?"
    r"(?:(?:re)?acquir(?:e[sd]?|ing)|buy[s]?|bought|purchase[sd]?)|"
    r"(?:to|agrees? to|plans? to|(?:has )?entered into an agreement to) (?:buy|acquire)|"
    r"(?:has )?(?:completed|closes?) (?:its |the )?acquisition of|"
    r"['’]?\s*s (?:first )?acquisition (?:of|was))\s*",
    re.I,
)
ACQUIRED_BY = re.compile(
    r'\s*[,:(]?\s*(?:(?:was |is |were |has been |to be )?'
    r'(?:acquired|bought|purchased)|(?:has )?(?:agreed|entered into an agreement) to be acquired)'
    r' by\s*', re.I,
)
RATINGS = re.compile(
    r'\b(?:upgrades?|downgrades?|upgraded|downgraded|initiates(?: coverage (?:of|on))?|'
    r'reiterates|maintains|raises|cuts|lowers|lifts)\b', re.I,
)
RATING_CONTEXT = re.compile(
    r'\b(?:buy|sell|hold|neutral|overweight|underweight|outperform|underperform|'
    r'price target|rating|shares|stock|equal[ -]?weight|market perform|sector perform)\b', re.I,
)
RATING_TARGET_LIST = re.compile(r'\s*(?:,\s*(?:and\s+)?|and\s+|&\s*)', re.I)
DIRECTIONAL_RATINGS = {'upgrade', 'upgrades', 'downgrade', 'downgrades'}
PRICE_TARGET_ACTIONS = {'raises', 'cuts', 'lowers', 'lifts'}
BROKER_GAP = re.compile(r'\b(?:at|by|from)\s*$', re.I)
PREVIEW = re.compile(r'\b(?:(?:to|will|set to) report|earnings preview|'
                     r'announces (?:the )?(?:date|conference call|webcast)|'
                     r'schedules? (?:its )?earnings)\b', re.I)
RESULTS = re.compile(r'\b(?:reports?|announces|posts|beats?|misses|tops)\b', re.I)
METRIC = re.compile(r'\b(?:earnings|financial results|operating results|eps|revenue|net loss)\b', re.I)
COMPARISON = re.compile(r'\b(?:vs\.?|versus|beats?|misses|above|below)\b', re.I)
ESTIMATE = re.compile(r'\b(?:consensus|est\.?|estimates?|expectations?)\b', re.I)
QUALIFIED_TICKER = (
    r'(?P<exchange>(?i:NASDAQ|NYSE AMERICAN|NYSE|TSXV|TSX|LSE|HKEX|ASX))'
    r'\s*:\s*(?P<ticker>[A-Z0-9][A-Z0-9.\-]{0,11})'
)
EXCHANGE_TICKER = re.compile(r'\(\s*' + QUALIFIED_TICKER + r'\s*\)')
BODY_TICKER_GROUP = re.compile(r'\(([^()]{1,120})\)')
BODY_TICKER = re.compile(QUALIFIED_TICKER)
DATELINE = re.compile(r'\s*' + EXCHANGE_TICKER.pattern)
PURCHASE_OBJECT = re.compile(
    r"\s*(?:['’]s\b|(?:stock|shares?|bonds?|products?|services?|assets?)\b)", re.I,
)


def body_ticker_hints(lead):
    for group in BODY_TICKER_GROUP.finditer(lead):
        # Require the entire parenthetical to be a list of qualified tickers.
        matches = list(BODY_TICKER.finditer(group[1]))
        end = 0
        for match in matches:
            gap = group[1][end:match.start()].strip()
            if gap != (',' if end else ''):
                break
            end = match.end()
        else:
            if matches and not group[1][end:].strip():
                for match in matches:
                    yield dict(start=group.start(1) + match.start(),
                               end=group.start(1) + match.end(), group_start=group.start(),
                               exchange=match['exchange'].upper(), ticker=match['ticker'])


GUIDANCE = re.compile(
    r'\b(?:raises|cuts|lowers|lifts|withdraws|reaffirms|boosts)\b'
    r'[^.;:]{0,50}\b(?:guidance|outlook)\b', re.I,
)
CAPITAL_RETURN = re.compile(
    r'\b(?:declares|announces|raises|cuts|suspends|authorizes)\b'
    r'[^.;:]{0,50}\b(?:dividend|buyback|share repurchase)\b', re.I,
)


MONTHS = ('jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec')
WIRE = r'(?P<wire>prnewswire|globe\s*newswire|business wire|accesswire|newsfile(?: corp\.)?)'
WIRE_DATE = (
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
    r"\.?\s+[0-9]{1,2},\s*20[0-9]{2}"
)
WIRE_DATELINE = re.compile(
    rf"\b(?P<date>{WIRE_DATE})\s*[/\(]\s*{WIRE}\s*[/\)]"
    rf"|/\s*(?P<prefix_wire>accesswire|newsfile(?: corp\.)?)\s*/\s*"
    rf"(?P<prefix_date>{WIRE_DATE})\s*/",
    re.I,
)


def wire_dateline(body):
    match = WIRE_DATELINE.search(body[:240])
    if not match:
        return None
    month_text, day_text, year_text = (match['date'] or match['prefix_date']).replace(',', ' ').split()
    try:
        month = MONTHS.index(month_text[:3].lower()) + 1
        day = date(int(year_text), month, int(day_text))
    except ValueError:
        return None
    return dict(date=day.isoformat(), wire=match['wire'] or match['prefix_wire'], precision='day',
                start=match.start(), end=match.end(), text=match[0])


WIRE_LEAD_GAP = re.compile(r'[\s,.:–—-]*')
ANNOUNCEMENT = re.compile(
    r'\s*,?\s*(?:(?:today|has)\s+)?'
    r'(?:announces?|announced|reports?|reported|releases?|released|publishes|published|'
    r'declares?|declared|provides?|provided)\b',
    re.I,
)

EARNINGS_REFERENCE = re.compile(
    r'\b(?:(?:financial|operating) results|earnings|results for (?:its |the )?'
    r'(?:first|second|third|fourth) quarter)\b', re.I,
)
EARNINGS_SCHEDULE = re.compile(
    r'\b(?:(?:will|plans to|expects to|is scheduled to) (?:report|release|publish|announce)'
    r'|(?:the )?date (?:for|of))\b', re.I,
)
DIRECT_RESULTS = re.compile(r'\s*(?:its |the )?(?:(?:financial|operating) results|'
                            r'earnings|results for)\b', re.I)


def wire_announcer(body, dateline, names, tickers):
    for name in names:
        if name['start'] < dateline['end']:
            continue
        if not WIRE_LEAD_GAP.fullmatch(body[dateline['end']:name['start']]):
            return None
        adjacent = [ticker for ticker in tickers
                    if ticker['group_start'] >= name['end']
                    and WIRE_LEAD_GAP.fullmatch(body[name['end']:ticker['group_start']])]
        if not adjacent:
            return None
        closing = body.find(')', adjacent[-1]['end'])
        if closing == -1:
            return None
        cue = ANNOUNCEMENT.match(body, closing + 1)
        if cue:
            context = re.split(r'[;!?\n]', body[cue.end():cue.end() + 160], maxsplit=1)[0]
            kind = 'other_announcement'
            if EARNINGS_REFERENCE.search(context):
                if EARNINGS_SCHEDULE.search(context):
                    kind = 'earnings_schedule_candidate'
                elif DIRECT_RESULTS.match(context):
                    kind = 'earnings_release_candidate'
            return dict(frame='wire_issuer_announcement', announcement_kind=kind,
                        roles=[name | {'role': 'announcing_issuer_candidate'}],
                        ticker_offsets=[ticker['start'] for ticker in adjacent],
                        cue=dict(start=cue.start(), end=cue.end(), text=cue[0]))
        return None


def acquisitions(text, spans):
    """Find clear adjacent acquirer/target pairs, retaining direction."""
    for left, right in zip(spans, spans[1:]):
        gap = DATELINE.sub('', text[left.end:right.start], count=1)
        gap = gap.replace('\xa0', ' ')
        if len(gap) > 120:
            continue
        if ACQUIRES.fullmatch(gap):
            target_suffix = DATELINE.sub('', text[right.end:right.end + 60], count=1)
            if not PURCHASE_OBJECT.match(target_suffix):
                yield left, right
        elif ACQUIRED_BY.fullmatch(gap):
            yield right, left


def adjacent(text, start, end):
    return bool(re.fullmatch(r"[\s'’:,\-]*(?:s\s*)?", text[start:end], re.I))


def event_frames(text, spans, broker_ids):
    for acquirer, target in acquisitions(text, spans):
        yield 'acquisition', [(acquirer, 'acquirer'), (target, 'target')]
    for trigger in RATINGS.finditer(text):
        before = next((s for s in reversed(spans) if s.end <= trigger.start()), None)
        after = next((s for s in spans if s.start >= trigger.end()), None)
        if not before or not after or after.start - before.end > 100:
            continue
        if not adjacent(text, before.end, trigger.start()):
            continue
        if broker_ids.intersection(before.evidence_ids) and adjacent(text, trigger.end(), after.start):
            action = trigger[0].lower()
            targets = [after]
            if action in DIRECTIONAL_RATINGS:
                for span in spans[spans.index(after) + 1:]:
                    gap = DATELINE.sub('', text[targets[-1].end:span.start], count=1)
                    if not RATING_TARGET_LIST.fullmatch(gap):
                        break
                    targets.append(span)
            context = re.split(r'[;!?]', text[targets[-1].end:targets[-1].end + 70], maxsplit=1)[0]
            if action in PRICE_TARGET_ACTIONS and not re.search(r'\bprice target\b', context, re.I):
                continue
            if len(targets) > 1 or action.startswith("initiates coverage") or RATING_CONTEXT.search(context):
                yield 'analyst_action', [(before, 'broker')] + [
                    (target, 'affected_issuer') for target in targets
                ]
        elif (trigger[0].lower() in {'upgraded', 'downgraded'}
              and broker_ids.intersection(after.evidence_ids)
              and BROKER_GAP.search(text[trigger.end():after.start])):
            yield 'analyst_action', [(after, 'broker'), (before, 'affected_issuer')]
    if not spans:
        return
    issuer = spans[0]
    if issuer.start > 12:
        return
    following = text[issuer.end:]
    dateline = DATELINE.match(following)
    if dateline:
        following = following[dateline.end():]
    # Another named party can be the subject of later headline clauses.
    issuer_clause = text[issuer.end:spans[1].start] if len(spans) > 1 else text[issuer.end:]
    for pattern, frame in ((GUIDANCE, 'guidance_change'), (CAPITAL_RETURN, 'capital_return')):
        if pattern.search(issuer_clause[:110]):
            yield frame, [(issuer, 'issuer')]
    if PREVIEW.search(following[:75]) and METRIC.search(following[:130]):
        yield 'earnings_preview', [(issuer, 'issuer')]
        return
    trigger = RESULTS.search(following[:50])
    if trigger and METRIC.search(following[:130]):
        event = ('earnings_estimate_comparison'
                 if COMPARISON.search(following) and ESTIMATE.search(following)
                 else 'reported_results_candidate')
        yield event, [(issuer, 'issuer')]


def headline_spans(headline, index):
    publisher = PUBLISHER_SUFFIX.search(headline)
    return index.find(headline[:publisher.start()] if publisher else headline)


def extract(row, index, broker_ids):
    headline = row['headline']
    title_spans = headline_spans(headline, index)
    events = list(event_frames(headline, title_spans, broker_ids))
    # Keep lead evidence distinct from headline offsets and from verified identity.
    body = (row.get('body') or '')[:1600]
    def mention(text, span):
        return dict(start=span.start, end=span.end, text=text[span.start:span.end],
                    evidence_ids=span.evidence_ids)
    result = dict(
        news_id=row['news_id'], rule_version=RULE_VERSION,
        headline_mentions=[mention(headline, s) for s in title_spans],
        headline_ticker_hints=[dict(start=match.start(), end=match.end(),
                                    exchange=match['exchange'].upper(), ticker=match['ticker'])
                               for match in EXCHANGE_TICKER.finditer(headline)],
        body_lead_mentions=[mention(body, s) for s in index.find(body)],
        body_lead_ticker_hints=list(body_ticker_hints(body)),
        events=[dict(frame=frame, roles=[mention(headline, span) | {'role': role}
                                       for span, role in roles])
                for frame, roles in events],
    )
    dateline = wire_dateline(body)
    if dateline:
        result['body_dateline_candidate'] = dateline
        announcement = wire_announcer(body, dateline, result['body_lead_mentions'],
                                      result['body_lead_ticker_hints'])
        if announcement:
            result['body_events'] = [announcement]
    return result


def mask_headline(headline, mentions, broker_ids):
    """Replace matched text while keeping offsets in the original headline."""
    pieces = []
    cursor = 0
    for mention in mentions:
        start, end = mention['start'], mention['end']
        ids = mention['evidence_ids']
        if len(ids) != 1:
            label = 'AMBIGUOUS'
        elif ids[0] in broker_ids:
            label = 'BROKER'
        else:
            label = 'ISSUER'
        pieces.extend((headline[cursor:start], f'[{label}]'))
        cursor = end
    pieces.append(headline[cursor:])
    return ''.join(pieces)
