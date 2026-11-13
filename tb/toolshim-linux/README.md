# Linux tool shims

`$OSS_CAD_SUITE/bin/vvp` does two things. It runs the real binary through the
suite's bundled dynamic loader:

```bash
exec .../lib/ld-linux-x86-64.so.2 --inhibit-cache --inhibit-rpath "" \
     --library-path .../lib .../libexec/vvp "$@"
```

The suite ships its own glibc, so that invocation isn't optional:
`libexec/vvp` run directly fails with `libvvp.so.1: cannot open shared object
file`. But the same wrapper exports `PYTHONHOME` at the suite, forcing cocotb
onto its bundled Python 3.11, which has no numpy.

These shims are that invocation without the `PYTHONHOME` export. `bin/iverilog`
sets no `PYTHONHOME`, so only `vvp` strictly needs this; the `iverilog` shim
exists so `VVP_EXECUTABLE` points here rather than at the suite's wrapper.

macOS needs none of this. `libexec/vvp` names its library as
`@executable_path/../lib/libvvp.1.14.0.dylib` and resolves relative to itself,
so `ICARUS_BIN_DIR` points straight at `libexec`. `env.sh` picks per platform.
