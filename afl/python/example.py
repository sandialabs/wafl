import afl
from binascii import hexlify
import sys

@afl.post_fuzz_callback
def f(id, fault, buf, cov, splicing_with, mutation_seq):
    print "*", id, fault, hexlify(buf[:16]), hexlify(cov[:16])

@afl.new_entry_callback
def f(id, fault, fn, alias_fn, buf, cov):
    print "+", id, fault, fn, alias_fn, hexlify(buf[:16]), hexlify(cov[:16])

@afl.notify_callback
def f(_type, _id):
    if _type == afl.NOTIFY_CYCLE_START:
        s = "| cycle(%d) start" % _id
    elif _type == afl.NOTIFY_CYCLE_END:
        s = "| cycle(%d) end" % _id
    elif _type == afl.NOTIFY_SEED_START:
        s = "| seed(%d) start" % _id
    elif _type == afl.NOTIFY_SEED_END:
        s = "| seed(%d) end" % _id
    else:
        raise ValueError("unknown notify type %d" % _type)
    print s

if __name__ == "__main__":
    pass
