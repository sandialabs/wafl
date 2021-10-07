import numpy as np
import struct
import random

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

def read_alias(path):
    def read_fmt(fmt, f):
        return struct.unpack(fmt, f.read(struct.calcsize(fmt)))
    with open(path, 'rb') as f:
        length = read_fmt('@I', f)[0]
        print(length)
        alias = np.frombuffer(f.read(length * 4), dtype=np.uint32, count=length)
        prob = np.frombuffer(f.read(length * 4), dtype=np.uint32, count=length)
    return alias, prob

# This class can be used to read and sample from the saved alias tables in
# out/queue/.state/offset_weights/
class AliasTable(object):

    def __init__(self, alias, prob):
        super().__init__()
        self.table_prob_list = list(range(prob.size))
        self.table_alias = alias
        self.table_prob = prob

    # this routine is from Vose-Alias-Method, with ALIAS_MAX modification
    def alias_generation(self):
        """ Return a random outcome from the distribution. """
        # Determine which column of table_prob to inspect
        col = random.choice(self.table_prob_list)

        # Determine which outcome to pick in that column
        # if self.table_prob[col] >= random.uniform(0,1):
        if self.table_prob[col] >= random.randint(0, ALIAS_MAX-1):
            return col
        else:
            return self.table_alias[col]

    # this routine is from Vose-Alias-Method
    def sample_n(self, size):
        """ Return a sample of size n from the distribution."""
        # Ensure a non-negative integer as been specified
        n = int(size)
        if n <= 0:
            raise ValueError("Please enter a non-negative integer for the number of samples desired: %d" % n)

        return [self.alias_generation() for i in range(n)]
