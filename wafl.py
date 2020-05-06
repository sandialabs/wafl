import numpy as np
import os
from wafl_interface import WAflInterface
from util import fast_hash
import json
import shutil

from collections import Counter,defaultdict

COV_MAX_SIZE = 65536

# CONSTANTS to depict change in coverage
COV_NO_CHANGE = -1
COV_CHANGE = 0
COV_INCREASE = 1
COV_SOFT_INCREASE = 2
COV_SOFT_DECREASE = 3
COV_DECREASE = 4

class MultiStats():
    def __init__(self):
        self.seed_cov = defaultdict(Counter)
        self.cov_change = Counter()
        self.spliced = Counter()

    def dump(self, fname):
        for attr in vars(self):
            with open("{}_{}".format(fname,attr), 'wb') as f:
                json.dump(getattr(self,attr), f)

    def witness_training(self, seed, buf, cov, splicing_with):
        # TODO would be nice to get the exec_cksum from afl
        h = fast_hash(cov)
        self.seed_cov[seed][h] +=1
        self.spliced.update([splicing_with])

    def witness_cov_change(self, change_type):
        self.cov_change[change_type] +=1

class WAflModel(WAflInterface):

    def __init__(self, save_incremental_dir=None, stats=None, alpha = 0.5,beta=0.4, gamma=0.3, delta=0.2, epsilon=0.1, profile=None):
        """
        Seeds is a list of buffers, optional

        """

        super(WAflModel, self).__init__()

        self.seed_table = {} # structure will be {seed_id: bytes}#
        self.weight_table = {} # structure will be {seed_id: np.zeros(len(seed), dtype=np.float64)
        self.latest_cov = {} # structure will be {seed_id: np.zeros(COV_MAX_SIZE), dtype=uint32}
        self.cov_counter = {}

        # Save off params for rewarding/penalizing training
        self.alpha = alpha
        self.beta = beta
        self.gamma = gamma
        self.delta = delta
        self.epsilon = epsilon

        # other
        self.profile = profile
        self.stats = stats
        self.curr_cycle = None
        self.save_incremental_dir = save_incremental_dir
        if self.save_incremental_dir:
            try: os.mkdir(self.save_incremental_dir)
            except OSError: pass

    def binarize_cov(self,cov):
        cov = np.frombuffer(cov, dtype=np.uint8)
        return np.where(cov==0,cov, 1)

    def got_new_seed(self, seed_id, buf, cov):
        """
        Model received a new seed to store away.

        :param seed_id: int
        :param buf: str
        :param cov: str
        :param path: str
        :return:
        """
        if seed_id in self.seed_table:
            print ("updating existing seed (id=%d, len=%d)." % (seed_id, len(buf)))
        else:
            print ("got new seed (id=%d, len=%d)." % (seed_id, len(buf)))
        self.seed_table[seed_id] = np.frombuffer(buf, dtype=np.uint8)
        self.weight_table[seed_id] = np.zeros(len(buf), dtype=np.float64)
        self.latest_cov[seed_id] = self.binarize_cov(cov)

    def get_weights(self, seed_id):
        """
        Given a x from AFL, calculate the weight vector of each byte.
        The weight vector is a set of w_1,w_2,...w_n where w_1 is the probability of that
        byte to be mutated. n is the length of x.

        If id is provided, use that seed's weight vector from weight_table.
        If None, calculate closest neighbor to x from weight_table.

        :param seed_id:
        :return: w, a numpy array of weights
        """
        if seed_id in self.weight_table:
            return self.weight_table[seed_id]
        else:
            raise KeyError("Cannot find the seed_id {} in the weight table. "
                              "It probably never got initialized.".format(seed_id))

    def calc_bytes_changed(self, seed_id, new_bytes):
        """
        (int, str) -> np.array

        Calculates the bytes that mutated from seed to new_bytes

        :param seed_id:
        :param new_bytes:
        :return: array of [0,0,1] where 1 is a byte change
        """
        seed_bytes = self.seed_table[seed_id]
        return new_bytes ^ seed_bytes

    def calc_cov_change(self, seed_id, cov_new):
        """
        (int, str) -> int
        Calculate the coverage change between latest stored coverage of seed_id and cov_new

        :param seed_id:
        :param cov_new:
        :return:
        """

        # TODO, think about this:             # if the branches that differed were ones that we've hit a lot before (relative "a lot"), should we reward that?
        cov_old = self.latest_cov[seed_id]
        cov_new = self.binarize_cov(cov_new)

        # NO CHANGE
        if len(cov_new) == len(cov_old) and np.all(cov_new == cov_old):
            return COV_NO_CHANGE

        # Determine if new coverage has kept old coverage despite the difference
        diff_cov = cov_new ^ cov_old
        change = cov_new[np.where(diff_cov)] == 1 # if the changed bits in the new coverage is not zero, we gained

        cov_new_sum = np.sum(cov_new)
        cov_old_sum = np.sum(cov_old)

        cov_return = None

        # ** Strict increase
        # There was a change and overall, coverage increased
        if (cov_new_sum > cov_old_sum) and np.all(change):
            # Since it was a strict increase, store this new increase
            self.latest_cov[seed_id] = cov_new
            cov_return = COV_INCREASE
        # ** Soft increase
        # There was a change and overall, the coverage didn't increase
        elif (cov_new_sum > cov_old_sum) and np.any(change):
            cov_return = COV_SOFT_INCREASE

        # ** Strict decrease
        # There was a change and overall, coverage decreased
        elif (cov_new_sum < cov_old_sum) and np.all(~change):
            cov_return = COV_DECREASE

        # ** Soft decrease
        # The coverage decreased but the coverage increased in another spot
        elif (cov_new_sum < cov_old_sum) and np.any(change):
            cov_return = COV_SOFT_DECREASE

        # ** Some change happened, but none of the above ones
        else:
            cov_return = COV_CHANGE

        if self.stats is not None:
            self.stats.witness_cov_change(cov_return)

        return cov_return


    def got_training(self, seed_id, new_bytes, cov_new, mutation_seq, splicing_with):
        """
        Given a buffer and edge coverage from AFL, update the seed_id's weights

        :param seed_id: ancestor seed that new_bytes came from
        :param new_bytes: byte buffer of mutated buffer
        :param cov_new: edge coverage of new_bytes
        :return:
        """

        # Get seed bytes
        seed_bytes = self.seed_table[seed_id]
        # TODO: Only calculate change if one ancestor. Handle this if too many instances where >1 ancestor
        # TODO: cannot handle different length seed and new bytes
        if splicing_with is None and len(seed_bytes) == len(new_bytes):
            new_bytes = np.frombuffer(new_bytes, dtype=np.uint8)
            # calculate bytes_changed from new_bytes
            bytes_changed = self.calc_bytes_changed(seed_id, new_bytes)

            cov_change = self.calc_cov_change(seed_id, cov_new)

            # if edge coverage increases
            if cov_change == COV_INCREASE:
                self.weight_table[seed_id] = self.weight_table[seed_id] + bytes_changed  # NUMBER 1 REWARD

            if cov_change == COV_SOFT_INCREASE:
                self.weight_table[seed_id] = self.weight_table[seed_id] + self.alpha*bytes_changed  # NUMBER 2 REWARD

            # if edge coverage changes, but didn't strictly increase
            if cov_change == COV_CHANGE:
                self.weight_table[seed_id] = self.weight_table[seed_id] + self.beta*bytes_changed # NUMBER 3 REWARD

            # if edge coverage changes, increases in some spots, but decreases overall
            if cov_change == COV_SOFT_DECREASE:
                self.weight_table[seed_id] = self.weight_table[seed_id] + self.gamma*bytes_changed # NUMBER 4 REWARD

            # if edge coverage changes, but decreases overall
            if cov_change == COV_DECREASE:
                self.weight_table[seed_id] = self.weight_table[seed_id] - self.delta * bytes_changed  # PENALTY

            # if edge coverage doesn't change, penalize here?
            # this is terrible outcome, says danny.
            if cov_change == COV_NO_CHANGE:
                self.weight_table[seed_id] = self.weight_table[seed_id] - self.epsilon*bytes_changed # PENALTY

            return cov_change

        if self.stats is not None:
            self.stats.witness_training(seed_id, new_bytes, cov_new, splicing_with)
       #     self.stats.dump(os.path.join(self.save_incremental_dir, 'testsave.stats'))


    def normalize_weights(self, weights):
        weights_sum = np.sum(weights)
        if weights_sum == 0:
            norm = weights
        else:
            norm = weights/weights_sum
        if norm.dtype != np.float64:
            return np.array(norm, dtype=np.float64)
        else:
            return norm

    def got_cycle_start(self, num):
        self.curr_cycle = num

    def got_cycle_end(self, num):
        """
        At the end of the cycle, write out the entire weight table
        :param num: int
        :return:
        """
        # Write out any stats and profile info
        if self.stats is not None and self.save_incremental_dir:
            self.stats.dump(os.path.join(self.save_incremental_dir, 'cycle%04d.stats' % num))
        if self.profile is not None and self.save_incremental_dir:
            self.profile.dump_stats(os.path.join(self.save_incremental_dir, 'cycle%04d.profile' % num))
            self.profile.enable()


    def got_seed_end(self, seed_id):
        """
        Once the seed is finished mutations, write out weights.

        :param seed_id: int
        :return:
        """
        weights = self.weight_table[seed_id]
        # normalize weights and write out to afl
        weights_norm = self.normalize_weights(weights)
        path = self.save_weights(seed_id, weights_norm)
        # save debug info
        self.save_incremental(path, weights_norm)

    def save_weights(self, seed_id, weights_norm):
        print ('saving weights for %d (len=%d)' % (seed_id, len(weights_norm)))
        return super(WAflModel, self).save_weights(seed_id, weights_norm)

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

    ###### FUTURE WORK #######
    def calc_nearest_seed(self, x):
        """
        Return the seed id with the closest distance to x
        :param x:
        :return:
        """
        # TODO
        return 0

    def smooth_weights(self, bytes, weights):
        """
        Use additive smoothing to smooth out weight vector
        This will become useful when we start to accept addition/deletion in bytes as mutations
        :param bytes:
        :param weights:
        :return:
        """
        if len(bytes) > len(weights):
            return np.concatenate([weights, np.ones(len(bytes)-len(weights))])



if __name__ == "__main__":
    import cProfile
    profile = cProfile.Profile()
    profile.enable()

    import argparse

    alpha = float(os.environ["WAFL_ALPHA"]) if "WAFL_ALPHA" in os.environ else 0.5
    beta = float(os.environ["WAFL_BETA"]) if "WAFL_BETA" in os.environ else 0.4
    gamma =  float(os.environ["WAFL_GAMMA"]) if "WAFL_GAMMA" in os.environ else 0.3
    delta =  float(os.environ["WAFL_DELTA"]) if "WAFL_DELTA" in os.environ else 0.2
    epsilon =  float(os.environ["WAFL_EPSILON"]) if "WAFL_EPSILON" in os.environ else 0.1
    savedir = os.environ["SAVE_DIR"] if "SAVE_DIR" in os.environ else None

    print ("Outputing incremental save to {}".format(savedir))
    if savedir is not None:
        with open("{}/params.csv".format(savedir), 'w') as fd:
            fd.write("alpha,beta,gamma,delta,epsilon\n")
            fd.write("{},{},{},{},{}\n".format(alpha,beta,gamma,delta,epsilon))

    wafl = WAflModel(
        alpha = alpha,
        beta = beta,
        gamma = gamma,
        delta = delta,
        epsilon = epsilon,
        stats=MultiStats(),
        profile=profile,
        save_incremental_dir=savedir)
