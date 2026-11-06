#!/usr/bin/env python3
"""Check a register of rulings: references that resolve, amendments readable
from both sides, and quotes that are the user's own words.

Usage: python3 tools/plan-check.py RULINGS [OTHER ...] [--transcript JSONL]
       python3 tools/plan-check.py --self-test

A register is a Markdown document holding entries "N. text", or "N, M. text"
for a merged entry, at line starts after its first "## " heading, and, before
that heading, a sentence beginning "Retired:" that lists the numbers dropped
("8, 16 and 50", "74 to 77"). An entry, and any OTHER document, cites entries
as "ruling N" or "rulings N, M and K to L". It prints, and exits 1 where 1 or 3
finds anything:

1. a reference, in RULINGS or an OTHER document, to a number that is neither
   an entry nor retired;
2. an entry citing another that does not cite it back, for eyeballing:
   a pointer may be one-way, an amendment may not, the amended entry read
   alone giving the old rule;
3. an entry number used twice;
4. (information) a reference to a retired number.

With --transcript, a Claude Code session's transcript, it also prints:

5. each double-quoted string of 12 characters or more in RULINGS, the quotes
   paired paragraph by paragraph, that occurs in none of the user's words:
   the messages typed at the prompt, those sent while the session worked, and
   the question dialog's answers with their questions, compaction summaries
   left out; whitespace collapsed, and " ... " splitting a quote into parts
   each of which must occur. For eyeballing: a quote of a commit subject or
   of a file's text is legitimate.

Exit 2: a usage error or a document that cannot be read. That the self-test
bites is mutants.py's to show.
"""
import json
import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

REF = re.compile(r'\b[Rr]ulings? (\d+(?:(?:, and |, | and | to )\d+)*)\b')


def flat(s):
    return ' '.join(s.split())


def refs(text):
    """The numbers a text cites as rulings: "rulings 1, 3 and 5 to 7"."""
    out = set()
    for lst in REF.findall(text):
        for a, b in re.findall(r'(\d+)(?: to (\d+))?', lst):
            out |= set(range(int(a), int(b or a) + 1))
    return out


def register(text):
    """A register's entries (number to flattened text), its retired numbers
    and the numbers used twice."""
    head, _, body = text.partition('\n## ')
    retired = set()
    m = re.search(r'Retired:(.*?)(?:\.\s|\.$|$)', flat(head))
    if m:
        lst = re.sub(r'\d{4}-\d\d-\d\d|\d+\.\d+', '', m.group(1))
        for a, b in re.findall(r'(\d+) to (\d+)', lst):
            retired |= set(range(int(a), int(b) + 1))
        retired |= {int(x) for x in re.findall(r'\d+', lst)}
    ents, dup = {}, []
    for mm in re.finditer(r'(?m)^(\d+(?:, \d+)*)\. (.*?)(?=^\d+(?:, \d+)*\. |^## |\Z)',
                          body, re.S):
        for n in map(int, mm.group(1).split(', ')):
            if n in ents:
                dup.append(n)
            ents[n] = flat(mm.group(2))
    return ents, retired, dup


def findings(docs):
    """Checks 1 to 4 over [(name, text)], the register first: their lines,
    and whether 1 or 3 found anything."""
    ents, retired, dup = register(docs[0][1])
    out, bad = [], False
    for name, text in docs:
        for n in sorted(refs(flat(text))):
            if n not in ents and n not in retired:
                out.append(f'1. {name}: ruling {n} is neither an entry nor retired')
                bad = True
    for n in sorted(set(dup)):
        out.append(f'3. entry {n} is numbered twice')
        bad = True
    for n, t in sorted(ents.items()):
        for r in sorted(refs(t) - {n}):
            if r in ents and n not in refs(ents[r]):
                out.append(f'2. {n} cites {r}, which does not cite {n} back')
            elif r in retired:
                out.append(f'4. {n} cites retired {r}')
    out.append(f'{len(ents)} entries, {len(retired)} retired numbers')
    return out, bad


def said(path):
    """The user's words in a transcript, whitespace collapsed."""
    words = []
    for line in open(path, encoding='utf-8'):
        if '"user"' not in line and '"queued_command"' not in line:
            continue
        try:
            o = json.loads(line)
        except ValueError:
            continue
        if o.get('isCompactSummary'):
            continue
        if o.get('type') == 'attachment':
            a = o.get('attachment') or {}
            if (a.get('type') == 'queued_command'
                    and (a.get('origin') or {}).get('kind') == 'human'
                    and isinstance(a.get('prompt'), str)):
                words.append(a['prompt'])
            continue
        if o.get('type') != 'user':
            continue
        c = (o.get('message') or {}).get('content')
        if isinstance(c, str):
            words.append(c)
            continue
        for b in c if isinstance(c, list) else []:
            if not isinstance(b, dict):
                continue
            if b.get('type') == 'text':
                words.append(b.get('text', ''))
            elif b.get('type') == 'tool_result':
                x = b.get('content')
                if not isinstance(x, str):
                    x = ' '.join(i.get('text', '') for i in x or []
                                 if isinstance(i, dict))
                if ('questions have been answered' in x
                        or x.startswith('The user answered')):
                    words.append(x)
    return flat('\n'.join(words))


def quotes(text, hay):
    """The register's quotes of 12 characters or more, and those not found."""
    qs = [q for para in re.split(r'\n\s*\n', text)
          for q in re.findall(r'"([^"]*)"', flat(para)) if len(q) >= 12]
    miss = [q for q in qs
            if not all(p.strip() in hay for p in q.split(' ... ') if p.strip())]
    return qs, miss


def self_test():
    """A scratch register, a document citing it and a transcript holding each
    form of the user's words, with every finding and missing quote required."""
    reg = ('# Rulings\n\nRetired: 7 and 9 to 11, their texts elsewhere. Run'
           ' python3 to check; next number 12.\n\n## Topic\n\n'
           '1. Use four CPUs. Words: "four" (M0, 2026-10-20 14:33); "use four'
           ' CPUs from now on" (M1). Status: amended by ruling 4.\n\n'
           '2. Never push. Words: "never push without my word" (D1); "never\n'
           'push ... my word" (M2). Status: in force; see ruling 6.\n\n'
           '3. A pointer to rulings 1 and 2. Status: in force.\n\n'
           '4. Six CPUs. Words: "you have six CPUs now" (Q1). Status: amends'
           ' ruling 1; rulings 2 to 3 stand.\n\n'
           '5. A first entry numbered 5.\n\n'
           '5. Cites ruling 9, retired, and ruling 1. Words: "this was only in'
           ' a summary" (M3). Status: in force.\n')
    other = 'See rulings 1, 2 and 8, ruling 7, ruling 10 and ruling 12.\n'
    want = {
        '1. plan.md: ruling 6 is neither an entry nor retired',
        '1. state.md: ruling 8 is neither an entry nor retired',
        '1. state.md: ruling 12 is neither an entry nor retired',
        '3. entry 5 is numbered twice',
        '2. 3 cites 1, which does not cite 3 back',
        '2. 3 cites 2, which does not cite 3 back',
        '2. 4 cites 2, which does not cite 4 back',
        '2. 4 cites 3, which does not cite 4 back',
        '2. 5 cites 1, which does not cite 5 back',
        '4. 5 cites retired 9',
        '5 entries, 4 retired numbers',
    }
    lines = [
        {'type': 'user', 'message': {'role': 'user',
                                     'content': 'use four CPUs from now on'}},
        {'type': 'attachment', 'attachment': {
            'type': 'queued_command', 'prompt': 'you have six CPUs now',
            'origin': {'kind': 'human'}}},
        {'type': 'user', 'message': {'role': 'user', 'content': [
            {'type': 'tool_result', 'tool_use_id': 'x',
             'content': 'The user answered: "Push?"="never push without my word"'}]}},
        {'type': 'user', 'isCompactSummary': True, 'message': {
            'role': 'user', 'content': 'this was only in a summary'}},
    ]
    bad = []
    got, fired = findings([('plan.md', reg), ('state.md', other)])
    if set(got) != want or not fired:
        bad.append(f'FAIL: findings {sorted(set(got) ^ want)} differ, fired {fired}')
    with tempfile.TemporaryDirectory() as t:
        tr = os.path.join(t, 'session.jsonl')
        with open(tr, 'w') as f:
            f.write(''.join(json.dumps(x) + '\n' for x in lines))
        qs, miss = quotes(reg, said(tr))
    if len(qs) != 5 or miss != ['this was only in a summary']:
        bad.append(f'FAIL: {len(qs)} quotes, missing {miss}; expected 5,'
                   ' missing only the summary\'s')
    for b in bad:
        print(b)
    if not bad:
        print('ok:   every finding and missing quote of the scratch register')
    return 1 if bad else 0


def main(argv):
    if argv == ['--self-test']:
        return self_test()
    tr = None
    if '--transcript' in argv:
        i = argv.index('--transcript')
        tr = argv[i + 1:i + 2]
        if not tr:
            print('--transcript wants a file', file=sys.stderr)
            return 2
        tr = tr[0]
        argv = argv[:i] + argv[i + 2:]
    if not argv:
        print(__doc__.split('\n\n')[1], file=sys.stderr)
        return 2
    common.require_readable(argv + ([tr] if tr else []))
    docs = [(p, open(p, encoding='utf-8').read()) for p in argv]
    out, bad = findings(docs)
    print('\n'.join(out))
    if tr:
        qs, miss = quotes(docs[0][1], said(tr))
        for q in miss:
            print(f'5. quote not in the user\'s words: "{q[:100]}"')
        print(f'{len(qs)} quotes, {len(miss)} not found')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
