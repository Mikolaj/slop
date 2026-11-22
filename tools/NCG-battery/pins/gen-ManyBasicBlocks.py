#!/usr/bin/env python3
# gen-ManyBasicBlocks.py OUT: the Cmm procedure !16269's genManyBasicBlocks describes
# (STAGES 2048, LOOP_PERIOD 16, LOOP_TRIPS 2): diamonds split/left/right/join,
# a latch per chunk of 16 stages jumping back to the chunk's first split.
# Written here from the script's text, which is not run.
import sys
STAGES, PERIOD, TRIPS = 2048, 16, 2
chunks = (STAGES + PERIOD - 1) // PERIOD
o = ['#include "Cmm.h"', '', 'many_basic_blocks (W_ seed) {', '  W_ acc;', '  W_ mix;']
o += [f'  W_ trip{c};' for c in range(chunks)]
o += ['', 'entry:', '  acc = seed;', '  mix = seed + (17 :: W_);']
o += [f'  trip{c} = 0;' for c in range(chunks)]
o += ['  goto split0;', '']
for s in range(STAGES):
    n, c = s + 1, s // PERIOD
    s1, s2, s3, s4 = 4 * s + 1, 4 * s + 2, 4 * s + 3, 4 * s + 4
    o += [f'split{s}:', f'  mix = mix + ({s1} :: W_);',
          f'  if (((mix + ({s2} :: W_)) % (7 :: W_)) < (3 :: W_)) {{',
          f'    goto left{s};', '  }', f'  goto right{s};', '',
          f'left{s}:', f'  acc = acc + ({s3} :: W_);', f'  mix = mix + ({s4} :: W_);',
          f'  goto join{s};', '',
          f'right{s}:', f'  acc = acc + ({s4} :: W_);', f'  mix = mix + ({s3} :: W_);',
          f'  goto join{s};', '',
          f'join{s}:', f'  acc = acc + mix + ({s1} :: W_);',
          f'  goto latch{c};' if n == STAGES or n % PERIOD == 0 else f'  goto split{n};', '']
for c in range(chunks):
    start, nxt = c * PERIOD, (c + 1) * PERIOD
    o += [f'latch{c}:', f'  trip{c} = trip{c} + (1 :: W_);',
          f'  mix = mix + ({1000000 + c} :: W_);', f'  acc = acc + ({2000000 + c} :: W_);',
          f'  if (trip{c} < ({TRIPS} :: W_)) {{', f'    goto split{start};', '  }',
          f'  goto split{nxt};' if nxt < STAGES else '  return (acc);', '']
o += ['}']
open(sys.argv[1], 'w').write('\n'.join(o) + '\n')
