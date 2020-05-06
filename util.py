import sys

try:
    # $ python -m timeit -s 'import numpy as np; a = np.arange(65536); import xxhash' 'xxhash.xxh32_intdigest(a)'
    # 10000 loops, best of 3: 67.3 usec per loop
    import xxhash
    def fast_hash(x):
        return xxhash.xxh32_intdigest(x)
except ImportError as e:
    # $ python -m timeit -s 'import numpy as np; a = np.arange(65536); import zlib' 'zlib.crc32(a)'
    # 1000 loops, best of 3: 339 usec per loop
    print >>sys.stderr, "couldn't import xxhash for fast hashes, falling back to zlib.crc32: %s" % (e)
    import zlib
    def fast_hash(x):
        return zlib.crc32(x) & 0xffffffff
