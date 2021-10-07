import afl
import alias_table

import numpy as np
import os

class WAflInterface(object):
    """This mixin class maps from the low level C/Python Afl api to the higher level WAfl api"""

    def __init__(self):
        afl.notify_callback(self._notify_callback)
        afl.post_fuzz_callback(self._post_fuzz_callback)
        afl.new_entry_callback(self._new_entry_callback)
        self._alias_paths = {}

    ### Low-Level API

    def _post_fuzz_callback(self, id, fault, buf, cov, splicing_with, mutation_seq, old_cksum, new_cksum):
        # TODO get the mutation_sequence from afl
        self.got_training(id, buf, cov, mutation_seq, None if splicing_with == -1 else splicing_with, old_cksum, new_cksum)

    def _new_entry_callback(self, id, fault, fn, alias_fn, buf, cov):
        self._alias_paths[id] = alias_fn.decode()
        # in case this is a "re-discover" of a trimmed seed, erase stale alias tables
        try: os.remove(alias_fn)
        except OSError: pass
        self.got_new_seed(id, buf, cov)

    def _notify_callback(self, _type, _id):
        if _type == afl.NOTIFY_CYCLE_END:
            self.got_cycle_end(_id)
        elif _type == afl.NOTIFY_SEED_END:
            self.got_seed_end(_id)
        elif _type == afl.NOTIFY_SEED_START:
            self.got_seed_start(_id)
        elif _type == afl.NOTIFY_CYCLE_START:
            self.got_cycle_start(_id)
        else:
            raise ValueError("unknown notification %d" % _type)

    ### WAfl API methods to be implemented by subclass

    def got_new_seed(self, seed_id, buf, cov):
        """This function will be called when wafl adds a new seed to the queue"""
        raise NotImplementedError

    def got_training(self, orig_seed_id, buf, cov, mutation_seq, splicing_with, old_cksum, new_cksum):
        """This function will be called when wafl mutates a buffer and
           calculates coverage for that buffer"""
        raise NotImplementedError

    def got_cycle_end(self, num):
        """This function will be called when a cycle completes"""
        pass

    def got_seed_end(self, num):
        """This function will be called when a seed is processed once in the queue"""
        pass

    def got_cycle_start(self, num):
        """This function will be called when a cycle start"""
        pass

    def got_seed_start(self, num):
        """This function will be called when a seed is about to be processed"""
        pass

    ### WAfl API methods

    def save_weights(self, seed_id, weights):
        """This function will save new weights for a seed.  Weights must be a
           np.float64 array of percentage probabilities for each offset."""
        assert weights.dtype == np.float64
        path = self._alias_paths[seed_id]
        alias, prob = alias_table.weights2alias(weights)
        alias_table.write_alias(alias, prob, path)
        return path
