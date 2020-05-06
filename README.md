# Summary
wafl is a modification of afl that tries to improve upon random fuzzing by
learning a probability distribution of offsets to fuzz.

## License                                                                         
Under Apache v 2.0, consistent with Google's licensing. 

# Dependencies

* Python 3 development packages
* numpy
* Vose-Alias-Method
* xxhash

```
sudo apt-get install python3-dev
# assuming pip is installed
pip3 install Vose-Alias-Method xxhash numpy
```

# Quick start

1. Clone this repo.
1. Update the submodule afl: `git submodule init`, then `git submodule update`
1. Make afl: `cd afl; make`
1. Run test example: `cd ../example_target; mkdir outdir; ./test_wafl.sh outdir`

