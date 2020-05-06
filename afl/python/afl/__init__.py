"""
Functions to interact with the running AFL instance.
"""

from __future__ import print_function

import _afl

NOTIFY_CYCLE_START     = 1
NOTIFY_CYCLE_END       = 2
NOTIFY_SEED_START      = 3
NOTIFY_SEED_END        = 4

# Keep track of registered functions to prevent users from overwriting
# a previously set callback
_new_entry_fn = None
_post_fuzz_fn = None
_notify_fn    = None

def notify_callback(fn):
    """Set a callback for when a cycle or seed change occurs."""
    global _notify_fn
    assert _notify_fn is None or fn is None
    _afl.set_notify_callback(fn)
    _notify_fn = fn
    return fn

def new_entry_callback(fn):
    """Set a callback for when new a new entry is added to the queue."""
    global _new_entry_fn
    assert _new_entry_fn is None or fn is None
    _afl.set_new_entry_callback(fn)
    _new_entry_fn = fn
    return fn

def post_fuzz_callback(fn):
    """Set a callback for when a new fuzz result is available."""
    global _post_fuzz_fn
    assert _post_fuzz_fn is None or fn is None
    _afl.set_post_fuzz_callback(fn)
    _post_fuzz_fn = fn
    return fn

def done(fn):
    import atexit
    """Set a callback for when AFL finishes."""
    atexit.register(fn)
    return fn

def quit(msg="done", code=0):
    """Print a message and quit the AFL main loop."""

    RESET_G1    = "\x1b)B"
    bSTOP       = "\x0f"
    CURSOR_SHOW = "\x1b[?25h"
    cRST        = "\x1b[0m"

    import sys
    print("%s %s %s %s\n%s" % (bSTOP, RESET_G1, CURSOR_SHOW, cRST, msg))
    sys.exit(code)
