#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#include <sys/types.h>
#include <sys/stat.h>
#include <fcntl.h>

#include "alloc-inl.h"
#include "config.h"
#include "types.h"
#include "debug.h"

struct alias {
  u8*  fname;                       /* File name for the weight vector  */
  u32  length;                      /* length of {alias,prob}_table     */
  u32* alias_table;                 /* the actual alias table           */
  u32* prob_table;                  /* the actual probability table     */
};

/* undefine to revert to standard UR() behavior */
#define ALIAS_USE_TABLES

/* some additional safety checks */
#define ALIAS_DO_CHECKS

/* stop rolling random numbers after this many tries */
#define ALIAS_MAX_RETRIES 5

#define ALIAS_THRESHOLD 32

// The probabilities in the probability table will be scaled from a float [0,1)
// to an integer [0,ALIAS_MAX).  Thus, (1./ALIAS_MAX) becomes our maximum
// precision and RAND_MAX needs to be at least as large as ALIAS_MAX. Needs to
// match the value in dist2alias.py.
#define ALIAS_MAX (unsigned)(1<<30)
_Static_assert(RAND_MAX >= ALIAS_MAX, "RAND_MAX needs to be bigger than ALIAS_MAX");

extern s32 dev_urandom_fd;
extern u32 rand_cnt;

/* Generate a random number (from 0 to limit - 1). This may
   have slight bias. */

static inline u32 UR(u32 limit) {

  if (unlikely(!rand_cnt--)) {

    u32 seed[2];

    ck_read(dev_urandom_fd, &seed, sizeof(seed), "/dev/urandom");

    srandom(seed[0]);
    rand_cnt = (RESEED_RNG / 2) + (seed[1] % RESEED_RNG);

#if 0
    printf("reseeding! next reseed: %d\n", rand_cnt);
#endif

  }

  return random() % limit;

}


/* Generate a random number according to the given alias table.  This
   is a fast method for picking random numbers according to an
   arbitrary non-uniform distribution.  For details see:

   * http://keithschwarz.com/darts-dice-coins/
   * https://lips.cs.princeton.edu/the-alias-method-efficient-sampling-with-many-discrete-outcomes/
   * https://github.com/asmith26/Vose-Alias-Method/

   */
static inline u32 UR_alias(u32 table_length, u32* alias_table, u32* prob_table) {
    // determine which column of prob_table to inspect
#if 1
    u32 col = UR(table_length);
#else
    // This code fixes a slight bias when using "random()%limit".  I think the
    // bias is small enough for the small buffer size (relative to ALIAS_MAX) to
    // not matter so sticking with the faster version for now.
    u32 col;
    u32 threshold = table_length*(RAND_MAX/table_length);
    do {
        col = random();
    } while(col >= threshold);
    col = col % table_length;
#endif

    // determine which outcome to pick in that column
    if(UR(ALIAS_MAX) <= prob_table[col])
        return col;
    else
        return alias_table[col];
}

/* Update the alias and probability tables.  Will allocate new tables if necessary. */

static void update_alias_table(char* fname, u32* table_length, u32** alias_table, u32** prob_table) {
    s32 fd = open(fname, O_RDONLY);
    if (fd < 0) {

        /* fail if we can't read the file and we don't have a table length */
        if(!*table_length) PFATAL("Unable to open '%s'", fname);

        u32 len = *table_length * sizeof(u32);

        /* alloc and init alias table if necessary */
        if(!*alias_table) {
            *alias_table = ck_alloc(len);
            /* initialize table to uniform */
            for(u32 i = 0; i < *table_length; i++) { (*alias_table)[i] = i; }
        }

        /* alloc and init probability table if necessary */
        if(!*prob_table) {
            *prob_table = ck_alloc(len);
            for(u32 i = 0; i < *table_length; i++) { (*prob_table)[i] = 0; }
        }

    } else {

        u32 new_length;
        ck_read(fd, &new_length, sizeof(new_length), fname);
        if(*table_length && new_length != *table_length)
            FATAL("length of alias table in '%s' changed from %d to %d", fname, *table_length, new_length);

        u32 len = new_length * sizeof(u32);
        if(!*alias_table) *alias_table = ck_alloc(len);
        if(!*prob_table) *prob_table = ck_alloc(len);
        ck_read(fd, *alias_table, len, fname);
        ck_read(fd, *prob_table, len, fname);
        close(fd);

        *table_length = new_length;

    }
}


/* Helper function to calculate a random number according to the given alias
   table. */

#ifndef ALIAS_USE_TABLES

static inline u32 URa(u32 limit, struct alias* alias) {
  (void)(alias);
  return UR(limit);
}

#else

static inline u32 URa(u32 limit, struct alias* alias) {

  u32 ret;
  u32 retries = ALIAS_MAX_RETRIES;

#ifdef ALIAS_DO_CHECKS
  if(!alias) FATAL("alias table is NULL");
  if(limit > alias->length) FATAL("alias table lengths got messed up");
#endif

  /* Skip the alias code on small buffers. This makes it less likely that we
  will do a bunch of retries trying to hit a single value in a small buffer. */
  if(limit < ALIAS_THRESHOLD) return UR(limit);

  do {
    ret = UR_alias(alias->length, alias->alias_table, alias->prob_table);
  } while(ret >= limit && (--retries) > 0);

#if 0
  if(ret >= limit) FATAL("reached max retries");
#endif

  /* fallback behavior */
  if(ret >= limit) return UR(limit);

  return ret;

}

#endif
