#!/bin/bash

echo "Starting at `date`"

set -eu

export AFL_SKIP_CPUFREQ=1
export AFL_NO_UI=1

outd="$1"
shift
ind=`dirname "$0"`
echo "input in ${ind} and output to ${outd}"
${ind}/../afl/afl-fuzz -d -m 200 -i $ind/in -o $outd/out -P "../wafl.py" -- ${ind}/zlib.afl

echo "Ending at `date`"

