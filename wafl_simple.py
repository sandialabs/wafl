from wafl_interface import WAflInterface
from util import fast_hash

import numpy as np
import os
import shutil
import json

from collections import namedtuple, Counter, defaultdict
Seed = namedtuple('Seed', ['buf', 'cov', 'id'])

class SimpleStats(defaultdict):
    def __init__(self, *args):
        if args:
            super(SimpleStats, self).__init__(*args)
        else:
            super(SimpleStats, self).__init__(Counter)

    def dump(self, fname):
        with open(fname, 'wb') as f:
            json.dump(self, f)

    def witness(self, seed, buf, cov):
        # TODO would be nice to get the exec_cksum from afl
        h = fast_hash(cov)
        self[seed][h] += 1

class SimpleScheme(object):
    def __init__(self, max_weight=100, min_weight=1, initial_weight=1, reward=1, penalty=-1):
        self.max_weight = max_weight
        self.min_weight = min_weight
        self.initial_weight = initial_weight
        self.reward = reward
        self.penalty = penalty
        # these checks are required to prevent under/overflow on a uint8
        if self.min_weight + self.penalty < 0:
            raise ValueError('min_weight + penalty must be >= 0')
        if self.max_weight + self.reward > 255:
            raise ValueError('max_weight + penalty must be <= 255')

    def initial_weights(self, buf, cov):
        return np.full(shape=len(buf), fill_value=self.initial_weight, dtype=np.uint8)

    def update_weights(self, w, orig_buf, orig_cov, new_buf, new_cov):
        """Update weights given a single training vector"""

        # we don't handle changed lengths
        if len(orig_buf) != len(new_buf): return

        # which bytes changed?
        x = np.frombuffer(orig_buf, dtype=np.uint8)
        y = np.frombuffer(new_buf, dtype=np.uint8)
        mask = (x!=y)

        # did the coverage change?
        if orig_cov != new_cov:
            adjustment = self.reward
            print("cov changed due to", mask.nonzero(), adjustment)
        else:
            adjustment = self.penalty

        # boost/penalize the changed bytes
        np.add.at(w, mask.nonzero(), adjustment)

        # prevent under/overflow
        np.clip(w, self.min_weight, self.max_weight, out=w)

    def normalize_weights(self, w):
        """Normalize weights to a probability distribution (sum to 1)"""
        n = w.astype(np.float64, copy=True)
        c = float(np.sum(w))
        n /= c
        return n


class WAflSimple(WAflInterface):
    def __init__(self, scheme=None, save_incremental_dir=None, stats=None, profile=None):
        super(WAflSimple, self).__init__()
        if scheme is None:
            scheme = SimpleScheme()
        self.stats = stats
        self.save_incremental_dir = save_incremental_dir
        self.seeds = {}
        self.weights = {}
        self.scheme = scheme
        self.curr_cycle = None
        self.profile = profile
        if self.save_incremental_dir:
            try: os.mkdir(self.save_incremental_dir)
            except OSError: pass

    def got_new_seed(self, seed_id, buf, cov):
        self.seeds[seed_id] = Seed(buf=buf, cov=cov, id=seed_id)
        self.weights[seed_id] = self.scheme.initial_weights(buf, cov)

    def got_training(self, orig_seed_id, buf, cov, mutation_seq, splicing_with, old_cksum, new_cksum):
        seed = self.seeds[orig_seed_id]
        weights = self.weights[orig_seed_id]
        self.scheme.update_weights(weights, seed.buf, seed.cov, buf, cov)
        if self.stats is not None: self.stats.witness(orig_seed_id, buf, cov)

    def got_cycle_start(self, num):
        self.curr_cycle = num

    def got_seed_end(self, seed_id):
        weights = self.weights[seed_id]
        norm = self.scheme.normalize_weights(weights)
        alias_fname = self.save_weights(seed_id, norm)
        self.save_incremental(alias_fname, norm)

    def got_cycle_end(self, num):
        if self.stats is not None and self.save_incremental_dir:
            self.stats.dump(os.path.join(self.save_incremental_dir, 'cycle%04d.stats' % num))
        if self.profile is not None and self.save_incremental_dir:
            self.profile.dump_stats(os.path.join(self.save_incremental_dir, 'cycle%04d.profile' % num))
            self.profile.enable()

    # mostly for debugging
    def save_incremental(self, alias_fname, norm):
        if self.save_incremental_dir:
            dest_dir = os.path.join(self.save_incremental_dir, 'cycle%04d' % self.curr_cycle)
            try: os.mkdir(dest_dir)
            except OSError: pass
            # save the alias table
            shutil.copy(alias_fname, dest_dir)
            # save the normalized weights
            weights_fname = '%s/%s.weights' % (dest_dir, os.path.basename(alias_fname))
            with open(weights_fname, 'wb') as f:
                f.write(norm.tobytes())

if __name__ == '__main__':
    import cProfile
    profile = cProfile.Profile()
    profile.enable()

    savedir = os.environ["SAVE_DIR"] if "SAVE_DIR" in os.environ else None

    wafl = WAflSimple(
        scheme=SimpleScheme(),
        # stats=SimpleStats(),
        # profile=profile,
        save_incremental_dir=savedir)
