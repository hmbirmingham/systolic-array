# Linux tool shims

cocotb needs two things at once from the Icarus binaries, and on Linux the
suite's own wrappers only give me one of them.

`$OSS_CAD_SUITE/bin/vvp` runs the real binary through the suite's **bundled
dynamic loader**:

```bash
exec .../lib/ld-linux-x86-64.so.2 --inhibit-cache --inhibit-rpath "" \
     --library-path .../lib .../libexec/vvp "$@"
```

The suite ships its own glibc and deliberately ignores the system ld cache and
rpaths, so that invocation is not optional — `libexec/vvp` run directly fails
with `libvvp.so.1: cannot open shared object file`.

But the same wrapper also exports `PYTHONHOME` to the suite, which forces
cocotb onto the suite's bundled Python 3.11. That interpreter has no numpy, and
every assertion I write compares against a NumPy golden model, so the oracle
becomes unreachable.

I need the loader and not the `PYTHONHOME`. These shims are the suite's own
invocation with that one export removed.

On macOS none of this is needed: `libexec/vvp` references its library as
`@executable_path/../lib/libvvp.1.14.0.dylib`, so it resolves relative to
itself and `ICARUS_BIN_DIR` can point straight at `libexec`. `env.sh` picks per
platform.
