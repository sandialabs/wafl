#include "config.h"
#include "types.h"
#include "debug.h"
#include "alloc-inl.h"
#include "hash.h"

#include <Python.h>
#include <libgen.h>

#if PY_MAJOR_VERSION >= 3
#define PYTHON3
#endif

// forward decls
static inline PyObject *
set_python_callback(PyObject *args, PyObject **py_callback);
static inline void
call_python_callback(PyObject* py_callback, PyObject* arglist, PyObject** out_result);

#define NOTIFY_CYCLE_START     1
#define NOTIFY_CYCLE_END       2
#define NOTIFY_SEED_START      3
#define NOTIFY_SEED_END        4

/* defined in afl-fuzz.c */
static void handle_stop_sig(int sig);

/* Same as FATAL but also call handle_stop_sig() to kill child processes. */
#define FATAL_WITH_STOP(x...) do { \
    SAYF(bSTOP RESET_G1 CURSOR_SHOW cRST cLRD "\n[-] PROGRAM ABORT : " \
         cBRI x); \
    SAYF(cLRD "\n         Location : " cRST "%s(), %s:%u\n\n", \
         __FUNCTION__, __FILE__, __LINE__); \
    handle_stop_sig(0); \
    exit(1); \
  } while (0)


// ****************************************

static PyObject *py_post_fuzz_callback = 0;

static PyObject *
py_set_post_fuzz_callback(PyObject *self, PyObject *args)
{
  return set_python_callback(args, &py_post_fuzz_callback);
}

static inline void
call_py_post_fuzz_callback(u32 id, u8 fault, u8* buf, u32 buf_len, u8* cov, u32 cov_len, u32 splicing_with, u8* seq, u32 seq_len, u32 old_cksum, u32 new_cksum) {

  if(!py_post_fuzz_callback) return;

  call_python_callback(py_post_fuzz_callback,
#ifdef PYTHON3
                       Py_BuildValue("(i, i, y#, y#, i, y#, i, i)", id, fault, buf, buf_len, cov, cov_len, splicing_with, seq, seq_len, old_cksum, new_cksum),
#else
                       Py_BuildValue("(i, i, s#, s#, i, s#, i, i)", id, fault, buf, buf_len, cov, cov_len, splicing_with, seq, seq_len, old_cksum, new_cksum),
#endif
                       NULL);
}

// ****************************************

static PyObject *py_new_entry_callback = 0;

static PyObject *
py_set_new_entry_callback(PyObject *self, PyObject *args)
{
  return set_python_callback(args, &py_new_entry_callback);
}

static inline void
call_py_new_entry_callback(
    u32 id, u8 fault,
    u8* fname, u32 fname_len,
    u8* alias_fname, u32 alias_fname_len,
    u8* buf, u32 buf_len,
    u8* cov, u32 cov_len) {

  if(!py_new_entry_callback) return;

  call_python_callback(py_new_entry_callback,
#ifdef PYTHON3
                       Py_BuildValue("(i, i, y#, y#, y#, y#)",
#else
                       Py_BuildValue("(i, i, s#, s#, s#, s#)",
#endif
                       id, fault,
                       fname, fname_len,
                       alias_fname, alias_fname_len,
                       buf, buf_len,
                       cov, cov_len),
                       NULL);
}

// ****************************************

static PyObject *py_notify_callback = 0;

static PyObject *
py_set_notify_callback(PyObject *self, PyObject *args)
{
  return set_python_callback(args, &py_notify_callback);
}

static inline void
call_py_notify_callback(u32 type, u32 val) {

  if(!py_notify_callback) return;

  call_python_callback(py_notify_callback,
                       Py_BuildValue("(i, i)", type, val),
                       NULL);
}

// ****************************************

// module definition

static PyMethodDef python_AflMethods[] = {
  {"set_post_fuzz_callback", py_set_post_fuzz_callback, METH_VARARGS,
   "Set the AFL post fuzz callback."},
  {"set_new_entry_callback", py_set_new_entry_callback, METH_VARARGS,
   "Set the AFL new entry callback."},
  {"set_notify_callback", py_set_notify_callback, METH_VARARGS,
   "Set the AFL notify callback."},
  {NULL, NULL, 0, NULL}
};

#ifdef PYTHON3

struct PyModuleDef python_AflModuleDef =
{
  PyModuleDef_HEAD_INIT,
  "_afl",
  "low level interface to afl",
  -1,
  python_AflMethods,
  NULL,
  NULL,
  NULL,
  NULL
};

/* This is called via the PyImport_AppendInittab mechanism called
   during initialization, to make the built-in _afl module known to
   Python.  */
PyMODINIT_FUNC init__afl_module (void);
PyMODINIT_FUNC
init__afl_module (void)
{
  return PyModule_Create (&python_AflModuleDef);
}

#endif

// ****************************************


/* Call a python callback, if registered. */

static inline void
call_python_callback(PyObject* py_callback, PyObject* arglist, PyObject** out_result)
{
  PyObject *result;

  if (py_callback == NULL) FATAL_WITH_STOP("py_callback == NULL");
  if (arglist == NULL && PyErr_Occurred()) {
    PyErr_Print();
    FATAL_WITH_STOP("arglist == NULL");
  }

  result = PyEval_CallObject(py_callback, arglist);
  if (PyErr_Occurred()) PyErr_Print();
  if (result == NULL) FATAL_WITH_STOP("error calling python callback");
  Py_DECREF(arglist);
  if(out_result)
    *out_result = result;
  else
    Py_DECREF(result);
}

/* set a new python callback */

static inline PyObject *
set_python_callback(PyObject *args, PyObject **py_callback)
{
  PyObject *result = NULL;
  PyObject *temp;

  if (py_callback == NULL) FATAL("py_callback == NULL");

  if (PyArg_ParseTuple(args, "O:set_callback", &temp)) {
    if (!PyCallable_Check(temp)) {
      PyErr_SetString(PyExc_TypeError, "parameter must be callable");
      return NULL;
    }
    Py_XINCREF(temp);          /* Add a reference to new callback */
    Py_XDECREF(*py_callback);  /* Dispose of previous callback */
    *py_callback = temp;       /* Remember new callback */
    /* Boilerplate to return "None" */
    Py_INCREF(Py_None);
    result = Py_None;
  }
  return result;
}

/* Start up the embedded python interpreter. */

static void init_python(int argc, char** argv) {
  PyObject *afl_module; // module "_afl"
  PyObject *afl_python_module; // module "afl"
  PyObject *m;
  PyObject *sys_path;
  int ret;

#ifdef PYTHON3
  PyImport_AppendInittab ("_afl", init__afl_module);
  Py_Initialize();
  const char* arg0 = argv[0];
  wchar_t* wargv[] = { Py_DecodeLocale(arg0, NULL), NULL };
  PySys_SetArgvEx(1, wargv, 0);
  afl_module = PyImport_ImportModule ("_afl");
#else
  Py_Initialize();
  PySys_SetArgvEx(argc,argv,0);
  afl_module = Py_InitModule ("_afl", python_AflMethods);
#endif

  if (PyErr_Occurred()) PyErr_Print();
  if (!afl_module) FATAL("could not initialize built-in _afl python module");

  /* TODO Consider looking in $(PREFIX)/share/afl/python as well */
  u8* afl_pythondir = getenv("AFL_PYTHON_DIR");
  if (!afl_pythondir) {
      char exepath[4096];
      ret = readlink("/proc/self/exe", exepath, sizeof(exepath));
      if(ret < 0) PFATAL("could not read /proc/self/exe, set AFL_PYTHON_DIR instead");
      char* afldir = dirname(exepath); /* this statement has side effects! */
      afl_pythondir = alloc_printf("%s/python", afldir);
  }

  sys_path = PySys_GetObject ("path");
  if (!(sys_path && PyList_Check (sys_path))) {
#ifdef PYTHON3
    PySys_SetPath (L"");
#else
    PySys_SetPath ("");
#endif
    sys_path = PySys_GetObject ("path");
  }
  if (sys_path && PyList_Check (sys_path)) {
    PyObject* pythondir = PyUnicode_FromString (afl_pythondir);
    if (!pythondir) FATAL("PyUnicode_FromString");
    int err = PyList_Insert (sys_path, 0, pythondir);
    Py_DECREF (pythondir);
    if (err) FATAL("PyList_Insert");
  }
  else {
    FATAL("sys_path");
  }

  afl_python_module = PyImport_ImportModule("afl");
  if (PyErr_Occurred()) PyErr_Print();
  if (!afl_python_module) FATAL("could not initialize built-in afl python module, check $AFL_PYTHON_DIR or %s/afl/__init__.py", afl_pythondir);

  m = PyImport_AddModule("__main__");
  if (PyErr_Occurred()) PyErr_Print();
  if (!m) FATAL("could not add __main__");

  Py_INCREF(afl_python_module);
  ret = PyModule_AddObject(m, "afl", afl_python_module);
  if (PyErr_Occurred()) PyErr_Print();
  if (ret) FATAL("could not add built-in afl python module to __main__");


}

/* Close down the embedded python interpreter. */

static void fini_python() {
  if(Py_IsInitialized())
    Py_Finalize();
}

/* Load a python file. */

static void load_python_file(char* pyfile) {

  FILE *fp;
  int ret;
  char* pyfile2 = ck_strdup(pyfile);
  char* dir = dirname(pyfile2);

  fp = fopen(pyfile, "r");
  if (!fp) PFATAL("opening python file \"%s\"", pyfile);

  /* allow relative imports by adding to sys.path */
  char* update_path = alloc_printf("import os, sys; sys.path.insert(1, os.path.abspath(\"%s\"))\n", dir);
  ret = PyRun_SimpleString(update_path);
  if (PyErr_Occurred()) PyErr_Print();
  if(ret) FATAL("python error occurred");

  ret = PyRun_SimpleFile(fp, pyfile);
  if (PyErr_Occurred()) PyErr_Print();
  if(ret) FATAL("python error occurred");

  fclose(fp);
  ck_free(pyfile2);
  ck_free(update_path);
}

// ****************************************
