import numpy as np
import struct

# pip install Vose-Alias-Method
from vose_sampler import VoseAlias

# needs to match the value in (afl's) random.h
ALIAS_MAX = 1<<30

def weights2alias(w):
    # np.array(dtype=float64) -> dict of {outcome:proportion}
    dist = dict(enumerate(w))

    # Convert a distribution (dict of {outcome:proportion}) into an alias table (alias, prob)
    va = VoseAlias(dist)
    length = len(va.table_prob_list)

    alias = np.arange(length, dtype=np.uint32)
    for k,v in va.table_alias.items():
        alias[k] = v

    prob = np.zeros(length, dtype=np.uint32)
    for k,v in va.table_prob.items():
        prob[k] = v * ALIAS_MAX

    return alias, prob

def write_alias(alias, prob, path):
    with open(path, 'wb') as f:
        f.write(struct.pack('@I', len(alias)))
        f.write(alias.tobytes())
        f.write(prob.tobytes())
