#!/usr/bin/env python3
"""Print the context, in tokens, of the conversation whose Bash call runs this:
a main session's or a subagent's.

    ctx-size.py [--cap N] WORD

WORD is a word unique to the call, typed literally in its command line, not
a shell expansion, which the transcript records unexpanded. The harness has
written the call's tool_use, WORD in it, into its conversation's transcript
under ~/.claude/projects by the time the command runs, so the tool takes
the transcript whose tail holds a Bash call with WORD in its command (a
parent's brief naming WORD is not one) and prints the input of the request
that made the call: its input, cache creation and cache read tokens
together, which is what each later call of that conversation re-reads.
With --cap, a context over N tokens adds "over the cap" and exits 3, else 0;
a WORD found in no transcript, or in more than one, exits 2.

Only the transcripts of CLAUDE_CODE_SESSION_ID's session are searched where
it is set, a subagent's Bash carrying its parent session's, and of each only
its last TAIL bytes, the call being its newest entry.
"""

import glob
import json
import os
import sys
import tempfile

ROOT = os.path.expanduser('~/.claude/projects')
TAIL = 8 << 20


def transcripts(root, session):
    if session:
        return (glob.glob(os.path.join(root, '*', session + '.jsonl'))
                + glob.glob(os.path.join(root, '*', session, 'subagents',
                                         '*.jsonl')))
    return glob.glob(os.path.join(root, '**', '*.jsonl'), recursive=True)


def runs_word(d, word):
    """Whether entry D is an assistant's Bash call whose command holds WORD:
    a parent's brief or a reply quoting the word is not the call."""
    if d.get('type') != 'assistant':
        return False
    content = d.get('message', {}).get('content')
    return isinstance(content, list) and any(
        c.get('type') == 'tool_use' and c.get('name') == 'Bash'
        and word in str((c.get('input') or {}).get('command', ''))
        for c in content if isinstance(c, dict))


def context_of(path, word):
    """The input tokens of the last Bash call in PATH's tail whose command
    holds WORD, or None."""
    with open(path, 'rb') as f:
        f.seek(max(0, os.path.getsize(path) - TAIL))
        tail = f.read().decode('utf-8', 'replace')
    found = None
    for line in tail.splitlines():
        if word not in line:
            continue
        try:
            d = json.loads(line)
        except ValueError:
            continue
        u = d.get('message', {}).get('usage') if runs_word(d, word) else None
        if u:
            found = (u.get('input_tokens', 0)
                     + u.get('cache_creation_input_tokens', 0)
                     + u.get('cache_read_input_tokens', 0))
    return found


def run(word, cap, root, session, out):
    hits = [(p, n) for p in transcripts(root, session)
            for n in [context_of(p, word)] if n is not None]
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
    """A session's main transcript and two subagents', the word in one
    subagent's Bash call and in the main transcript's brief and Monitor
    command: that call's sum
    is printed, the cap judged both ways, and an absent word or one in two
    transcripts' calls refused."""
    import io
    with tempfile.TemporaryDirectory() as root:
        sess = os.path.join(root, 'proj', 'S1')
        os.makedirs(os.path.join(sess, 'subagents'))

        def entry(word, i, c, r, tool='Bash', key='command'):
            return json.dumps({'type': 'assistant', 'message': {
                'usage': {'input_tokens': i, 'cache_creation_input_tokens': c,
                          'cache_read_input_tokens': r},
                'content': [{'type': 'tool_use', 'name': tool,
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
        checks = [
            (('w1', None), 0, 'context 252003 tokens (agent-a.jsonl)'),
            (('w1', 250000), 3, 'context 252003 tokens (agent-a.jsonl), over the cap of 250000'),
            (('w1', 252003), 0, 'context 252003 tokens (agent-a.jsonl)'),
            (('w9', None), 2, "ctx-size: 'w9' in 0 transcripts"),
            (('w0', None), 2, "ctx-size: 'w0' in 2 transcripts"),
        ]
        bad = 0
        for (word, cap), rc, want in checks:
            out = io.StringIO()
            got = run(word, cap, root, 'S1', out)
            if got != rc or not out.getvalue().startswith(want):
                print(f'FAIL {word} cap={cap}: exit {got}, {out.getvalue()!r}')
                bad += 1
        out = io.StringIO()
        if run('w2', None, root, 'S2', out) != 2:
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
