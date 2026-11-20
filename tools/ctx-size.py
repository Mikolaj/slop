#!/usr/bin/env python3
"""Print the context, in tokens, of the conversation whose Bash call runs this:
a main session's or a subagent's.

    ctx-size.py [--cap N] WORD

WORD is a word fresh to the call, typed literally in its command line, not
a shell expansion, which the transcript records unexpanded. The harness
writes the call's tool_use, WORD in it, into its conversation's transcript
under ~/.claude/projects as the command starts, for an unsandboxed command
as late as 0.09 s after (measured 2026-11-20), and its tool_result only when
the call returns. So the tool waits SETTLE seconds and takes the transcript
whose tail holds a Bash call with WORD in its command and no result yet (a
parent's brief naming WORD is not one, nor a finished call whose command
holds WORD too, another agent's or the caller's own), re-reading every
POLL seconds for up to RETRY more while it finds none. A call run in the
harness's background mode returns at once with a STUB, its only result, and
counts as running for good. The tool prints the input of the request that
made the call: its input, cache creation and cache read tokens together,
which is what each later call of that conversation re-reads.
With --cap, a context over N tokens adds "over the cap" and exits 3, else 0;
such a call in no transcript, or in more than one, exits 2.

Only the transcripts of CLAUDE_CODE_SESSION_ID's session are searched where
it is set, a subagent's Bash carrying its parent session's, and of each only
its last TAIL bytes, the call being its newest entry.
"""

import glob
import json
import os
import sys
import tempfile
import time

ROOT = os.path.expanduser('~/.claude/projects')
TAIL = 8 << 20
STUB = 'Command running in background with ID: '
SETTLE, RETRY, POLL = 0.5, 3.0, 0.15


def text_of(c):
    """The text of tool_result C's content, a string or a list of blocks."""
    r = c.get('content')
    if isinstance(r, list):
        return ''.join(b.get('text', '') for b in r if isinstance(b, dict))
    return r if isinstance(r, str) else ''


def transcripts(root, session):
    if session:
        return (glob.glob(os.path.join(root, '*', session + '.jsonl'))
                + glob.glob(os.path.join(root, '*', session, 'subagents',
                                         '*.jsonl')))
    return glob.glob(os.path.join(root, '**', '*.jsonl'), recursive=True)


def runs_word(d, word):
    """The ids of entry D's Bash calls whose command holds WORD, D being an
    assistant's: a parent's brief or a reply quoting the word is no call."""
    content = d['message'].get('content')
    if d.get('type') != 'assistant' or not isinstance(content, list):
        return []
    return [c.get('id') for c in content if isinstance(c, dict) and (
        c.get('type') == 'tool_use' and c.get('name') == 'Bash'
        and word in str((c.get('input') or {}).get('command', '')))]


def context_of(path, word):
    """The input tokens of the last Bash call in PATH's tail whose command
    holds WORD and which has no tool_result there but a STUB, or None."""
    with open(path, 'rb') as f:
        f.seek(max(0, os.path.getsize(path) - TAIL))
        tail = f.read().decode('utf-8', 'replace')
    calls, done = [], set()
    for line in tail.splitlines():
        if word not in line and 'tool_result' not in line:
            continue
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if not isinstance(d, dict) or not isinstance(d.get('message'), dict):
            continue
        content = d['message'].get('content')
        if isinstance(content, list):
            done.update(c.get('tool_use_id') for c in content
                        if isinstance(c, dict)
                        and c.get('type') == 'tool_result'
                        and not text_of(c).startswith(STUB))
        u = d['message'].get('usage')
        if u:
            calls += [(i, u.get('input_tokens', 0)
                       + u.get('cache_creation_input_tokens', 0)
                       + u.get('cache_read_input_tokens', 0))
                      for i in runs_word(d, word)]
    pending = [n for i, n in calls if i not in done]
    return pending[-1] if pending else None


def run(word, cap, root, session, out, settle=SETTLE, retry=RETRY):
    time.sleep(settle)
    deadline = time.monotonic() + retry
    while True:
        hits = [(p, n) for p in transcripts(root, session)
                for n in [context_of(p, word)] if n is not None]
        if hits or time.monotonic() >= deadline:
            break
        time.sleep(POLL)
    if len(hits) != 1:
        print(f'ctx-size: {word!r} in {len(hits)} transcripts, not one'
              + ''.join(f'\n  {p}' for p, _ in hits)
              + ('' if hits else '; type it literally, a fresh word'),
              file=out)
        return 2
    path, n = hits[0]
    over = cap is not None and n > cap
    print(f'context {n} tokens ({os.path.basename(path)})'
          + (f', over the cap of {cap}' if over else ''), file=out)
    return 3 if over else 0


def self_test():
    """A session's main transcript and five subagents', the word in one
    subagent's running Bash call, in another's finished one and in the main
    transcript's brief and Monitor command: the running call's sum
    is printed, the cap judged both ways, and an absent word or one in two
    transcripts' running calls refused; a call whose only result is a STUB,
    as a string or as a text block, is running. Those read with no wait;
    a caller's entry appended after the tool started is waited for, by the
    re-reads where no other running call holds its word and by the first
    wait where one does."""
    import io
    import threading
    with tempfile.TemporaryDirectory() as root:
        sess = os.path.join(root, 'proj', 'S1')
        os.makedirs(os.path.join(sess, 'subagents'))

        def entry(word, i, c, r, tool='Bash', key='command'):
            return json.dumps({'type': 'assistant', 'message': {
                'usage': {'input_tokens': i, 'cache_creation_input_tokens': c,
                          'cache_read_input_tokens': r},
                'content': [{'type': 'tool_use', 'name': tool,
                             'id': f'{word}-{i}-{c}-{r}-{tool}',
                             'input': {key: 'ctx-size.py ' + word}}]}})
        with open(sess + '.jsonl', 'w') as f:
            f.write(entry('w0', 1, 2, 300000) + '\n'
                    + entry('w1', 5, 5, 5, 'Agent', 'prompt') + '\n'
                    + entry('w1', 6, 6, 6, 'Monitor') + '\n')
        with open(os.path.join(sess, 'subagents', 'agent-a.jsonl'), 'w') as f:
            f.write(entry('w1', 1, 10, 100) + '\n'
                    + json.dumps({'type': 'user', 'message': {'content': 'w1'}}) + '\n'
                    + entry('w1', 3, 2000, 250000) + '\n')
        with open(os.path.join(sess, 'subagents', 'agent-b.jsonl'), 'w') as f:
            f.write(entry('w2', 1, 1, 1) + '\n' + entry('w0', 1, 1, 1) + '\n')
        def result(tid, content):
            return json.dumps({'type': 'user', 'message': {'content': [
                {'type': 'tool_result', 'tool_use_id': tid,
                 'content': content}]}})
        with open(os.path.join(sess, 'subagents', 'agent-c.jsonl'), 'w') as f:
            f.write(entry('w1', 7, 7, 7) + '\n'
                    + result('w1-7-7-7-Bash', 'context 21 tokens') + '\n')
        with open(os.path.join(sess, 'subagents', 'agent-d.jsonl'), 'w') as f:
            f.write(entry('w3', 8, 8, 8) + '\n'
                    + result('w3-8-8-8-Bash', STUB + 'b1.') + '\n'
                    + entry('w4', 9, 9, 9) + '\n'
                    + result('w4-9-9-9-Bash',
                             [{'type': 'text', 'text': STUB + 'b2.'}]) + '\n')
        with open(os.path.join(sess, 'subagents', 'agent-e.jsonl'), 'w') as f:
            f.write(entry('w4', 4, 4, 4) + '\n')
        checks = [
            (('w1', None), 0, 'context 252003 tokens (agent-a.jsonl)'),
            (('w1', 250000), 3, 'context 252003 tokens (agent-a.jsonl), over the cap of 250000'),
            (('w1', 252003), 0, 'context 252003 tokens (agent-a.jsonl)'),
            (('w9', None), 2, "ctx-size: 'w9' in 0 transcripts"),
            (('w0', None), 2, "ctx-size: 'w0' in 2 transcripts"),
            (('w3', None), 0, 'context 24 tokens (agent-d.jsonl)'),
            (('w4', None), 2, "ctx-size: 'w4' in 2 transcripts"),
        ]
        bad = 0
        for (word, cap), rc, want in checks:
            out = io.StringIO()
            got = run(word, cap, root, 'S1', out, 0, 0)
            if got != rc or not out.getvalue().startswith(want):
                print(f'FAIL {word} cap={cap}: exit {got}, {out.getvalue()!r}')
                bad += 1

        def late(name, line, after):
            def append():
                with open(os.path.join(sess, 'subagents', name), 'a') as f:
                    f.write(line + '\n')
            t = threading.Timer(after, append)
            t.start()
            return t
        with open(os.path.join(sess, 'subagents', 'agent-g.jsonl'), 'w') as f:
            f.write(entry('w6', 6, 6, 6) + '\n')
        for word, line, name, settle, retry, rc, want in [
                ('w5', entry('w5', 5, 5, 50), 'agent-f.jsonl', 0, 1.0, 0,
                 'context 60 tokens (agent-f.jsonl)'),
                ('w6', entry('w6', 1, 1, 1), 'agent-h.jsonl', 0.3, 0, 2,
                 "ctx-size: 'w6' in 2 transcripts")]:
            t = late(name, line, 0.1)
            out = io.StringIO()
            got = run(word, None, root, 'S1', out, settle, retry)
            t.join()
            if got != rc or not out.getvalue().startswith(want):
                print(f'FAIL late {word}: exit {got}, {out.getvalue()!r}')
                bad += 1
        out = io.StringIO()
        if run('w2', None, root, 'S2', out, 0, 0) != 2:
            print('FAIL: another session searched')
            bad += 1
    print('ctx-size self-test:', 'FAILED' if bad else 'ok')
    return 1 if bad else 0


def main(argv):
    if argv == ['--self-test']:
        return self_test()
    cap = None
    if len(argv) == 3 and argv[0] == '--cap' and argv[1].isdigit():
        cap, argv = int(argv[1]), argv[2:]
    if len(argv) != 1 or argv[0].startswith('-'):
        print(__doc__.split('\n\n')[1], file=sys.stderr)
        return 2
    return run(argv[0], cap, ROOT, os.environ.get('CLAUDE_CODE_SESSION_ID'),
               sys.stdout)


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
