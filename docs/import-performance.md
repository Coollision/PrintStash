# Measuring ZIP import performance

Use the complete archive as the benchmark input. From `backend/`:

```bash
uv run python scripts/bench_import.py /path/library.zip --output before.json
# Run again after changing the importer.
uv run python scripts/bench_import.py /path/library.zip --output after.json --compare before.json
```

Each run starts a fresh local server with migrated SQLite and temporary file
storage. It uploads the ZIP through the API, selects every supported file and
waits for the import to finish. The script checks the final file count and
failure count. A comparison also requires matching archive hashes and imported
file hashes and sizes. Preview outcome counts must also match. New reports
record dimensions, volume and triangle counts and compare those values too.

The timer includes upload, extraction and processing. Setup, database migration,
server startup and hashing the input archive are excluded. JSON output records
the separate timings, progress samples, API polling latency, Artifact job
statuses, server CPU time and sampled server memory use. Memory sampling runs
every 100 ms throughout upload, extraction and processing. It can miss shorter
peaks. RSS sums the server and its live subprocesses, so shared mappings can be
counted more than once. On Linux, CPU totals include reaped subprocesses as well
as live descendants. CPU seconds measure work across cores; elapsed seconds
measure how long the import takes. Run comparisons on the same machine with the
same settings, without other benchmarks or test suites running.

Reports also record the preview recipe hash, total encoded preview bytes and
the SHA256 of each decoded RGBA image, including its dimensions and state.
Image decoding and optional `--export-previews /path/previews` happen after
the timed interval. Export names include source and encoded hashes so different
outputs from the same source remain distinguishable.

Comparisons require identical compressed preview bytes by default. When testing
a lossless encoder change, use `--preview-comparison pixels` with `--compare`.
That mode requires a reference containing decoded pixel hashes and rejects any
changed pixel, dimensions or preview state. Imported source files and geometry
must still match. It does not allow reduced resolution or lossy compression.

Add `--similarity` to both commands to enable analysis on upload. ZIP imports
save files, geometry and previews before queuing optional similarity
analysis. The import timer ends when those files are available. It does not
measure completion of similarity analysis; pending fingerprint states are
recorded separately. The temporary server and its analysis queue are removed
after measurement. Use a persistent test vault to measure analysis through to
completion.

Similarity workers start no new work while an upload or another write operation
is active. A running analysis step can finish before it yields. Queued analysis
is stored in the database and survives an application
restart in a normal vault.

Use `--timeout 10800` for a three-hour limit when measuring a slow reference.
Small archives can identify regressions, but their timings do not establish
throughput or memory use for a 50 GB library.

## Compare Python and Rust

The optional `printstash-mesh-native` extension moves triangle coverage and
depth selection into Rust. It also parses 3MF mesh coordinates and face indices
from a stream, reads binary STL geometry, and measures mesh bounds and volume.
Both renderers use the same camera, normals, lighting and image
encoder. Stored and DEFLATE model parts inside 3MF packages are read and
decompressed in Rust using `zip`, `flate2` and `zlib-rs`. The XML parser reads
64 KiB buffers without Python callbacks and retains size limits and CRC checks.
Package inventory validation and scene assembly remain in Python. Older native
extensions and other compression methods retain the Python ZIP reader.
Outer ZIP extraction, STEP tessellation, storage and job coordination remain
in the existing pipeline.

Both Docker variants build and install the extension. Rebuild the image to use
it. For a source checkout, install Rust 1.88 or newer, then run from `backend/`:

```bash
uv sync --extra dev
uv pip install ./rust
```

The package uses [PyO3's Python bindings](https://pyo3.rs/v0.28.3/getting-started.html)
and an ABI3 wheel for Python 3.11 or newer. CI and the Docker builder use Rust
1.91. The Rust toolchain is only needed to build the wheel, not to run it.
Source installations without the extension retain the Python renderer.
An exact `uv sync` can remove this separately installed extension; install it
again afterward.

`VAULT_MESH_RASTERIZER` accepts `auto` (the default), `python` or `rust`.
`auto` uses Rust when the extension is installed. `python` provides an explicit
fallback. Budgeted STL recovery keeps its existing Python rasterizer and
partial-tile accounting in every mode.

Compare complete imports with explicit engines:

```bash
uv run python scripts/bench_import.py /path/library.zip --renderer python --output python.json
uv run python scripts/bench_import.py /path/library.zip --renderer rust --output rust.json --compare python.json
```

The report records the requested engine, selected engine and compiled module
hash. It also records generated preview hashes and checks them when the reference
contains them. Requesting Rust without the extension fails before the benchmark starts.
Add `--similarity` to both commands to compare the same import settings with
analysis enabled. Fingerprint completion remains outside this timer.

The native rendering kernels run on one thread and release the Python interpreter lock
while computing visibility, interpolating normals and applying the canonical
lighting. They accept immutable byte buffers and return packed final fragments
(pixel index, depth and RGB); they do not access storage or mutate Python arrays.
The fused path keeps face IDs inside Rust and avoids a separate visibility
payload and RGB result. Visibility memory is bounded by the framebuffer size.
The shader uses constant
per-pixel scratch space and allocates its RGB output at its final size, avoiding
NumPy arrays for barycentric interpolation, normalized normals and light terms.

Python still prepares vertex/corner normals and publishes the completed colors.
Custom lighting callbacks and older native extensions retain the Python shading
path with batches of at most 16,384 visible pixels. Both paths finish shading
before updating the caller's image or depth. Invalid native buffers, fragment
indices and lighting parameters are rejected before any framebuffer update.
Rust uses no unsafe blocks; PyO3 supplies the Python boundary.

The renderer still copies input buffers to give Rust immutable data while the
interpreter lock is released. Mesh loading and vertex preparation retain arrays
that grow with the individual mesh. These bounds do not make import memory
constant or establish performance for a 50 GB library.


## Streaming 3MF loading

`VAULT_MESH_LOADER` accepts `auto` (the default) or `python`. In `auto`, the
native parser reads model XML from the ZIP in blocks of at most 64 KiB. It
retains numeric vertex and face arrays plus the scene XML needed to place them.
It does not decompress unrelated previews or project settings. Source installs
without the parser use the existing Python loader; `python` selects that loader
explicitly.

The scene loader preserves repeated instances, component transforms and
references to other model parts in the package. It rejects missing references,
cycles and resource-limit violations instead of returning a partial scene.
The package must contain `3D/3dmodel.model`, as required by the existing loader.
Its default limits are 512 MiB of uncompressed package data, 4,096 ZIP members,
4,096 objects, 10,000 mesh instances and 512 MiB of expanded geometry arrays.
The XML parser also limits nesting to 256 levels and retained scene XML to
16 MiB per model part. These limits bound admitted work, not total process RSS.

The renderer discards back-facing and degenerate triangles before calculating
per-corner shading normals. Whole-mesh vertex normals still use all faces, so
this earlier culling retains the existing shading and silhouette behavior.
Geometry measurements and stored source files keep the complete mesh.

To isolate loading performance, keep the renderer fixed and import the complete
ZIP with each loader:

```bash
uv run python scripts/bench_import.py /path/library.zip --renderer rust --loader python --output legacy-load.json
uv run python scripts/bench_import.py /path/library.zip --renderer rust --loader auto --output streaming-load.json --compare legacy-load.json
```

The report records both loader selections. `--loader auto` selects Rust for 3MF
and binary STL when the corresponding parser is available. Other formats keep
their existing loaders. Scene assembly and rendering still retain arrays
proportional to the mesh size. Streaming does not make the whole pipeline use
constant memory.


## Binary STL and geometry measurements

The native binary STL loader reads the file in 64 KiB blocks and writes
coordinates and face indices directly into their final buffers. It preserves
stored triangle order and rejects nonfinite coordinates. Binary detection uses
the declared triangle count and file length, so a binary header beginning with
`solid` still loads correctly. ASCII STL uses the existing loader. The native
loader limits both file bytes and expanded vertex/index buffers to 512 MiB;
application admission limits still apply before loading.

`VAULT_MESH_GEOMETRY` accepts `auto` (the default) or `python`. When the native
function is installed, `auto` measures the bounds of referenced vertices and
the signed surface volume in blocks of at most 65,536 faces. It avoids computing
unused inertia and center-of-mass arrays. Dimensions and positive volumes keep
the existing rounding to two decimal places. Missing or older extensions use
the existing measurements.

The geometry calculation retains the existing convention for open surfaces;
it does not turn an open mesh into a watertight solid. STEP tessellation still
uses its existing worker, after which the native measurements can process the
resulting triangles. The source files and rendering quality are unchanged.

Use `--geometry python` or `--geometry auto` in the complete-ZIP benchmark to
compare measurement engines while keeping the loader and renderer fixed. The
report records the selected engine and checks saved geometry values against
the reference. `VAULT_MESH_LOADER=python` separately selects the previous STL
and 3MF loaders.


Native STL previews also verify mesh reclamation through a weak reference.
They first collect younger object cycles and run a full collection if the mesh
is still alive. This avoids repeatedly scanning unrelated long-lived objects.
The allocator still returns freed pages to the OS. Scene loaders and fingerprint
analysis retain the existing full collection because they can create additional
mesh copies.

## Lossless preview compression

Preview recipe version 3 uses WebP method 0 for both rendered and normalized
embedded images. It preserves every RGBA value, including colors under fully
transparent pixels, while spending less CPU time on compression. The tradeoff
is larger thumbnail files. The previous recipe used method 6, which spent more
CPU time looking for smaller encodings.

The canonical recipe is shared with the generated frontend profile. Its new
fingerprint keeps newly generated thumbnails separate from previous outputs;
existing thumbnail objects remain immutable. The encoder is the existing native
WebP library. Rust continues to handle the mesh operations described above.

## Adaptive archive workers

ZIP imports compute mesh geometry and previews ahead of the ordered writer.
`VAULT_IMPORT_WORKERS=0` selects the worker count automatically. It uses roughly
half the effective CPU allocation, honors CPU affinity and cgroup quotas, and
requires 512 MiB of mesh budget per worker. The count is capped at 32. Set it to
`1` for serial execution, or a positive number to request a higher ceiling;
CPU and memory limits still apply. `VAULT_MAX_RENDER_JOBS` continues to govern
other mesh operations; use `VAULT_IMPORT_WORKERS=1` to serialize ZIP computation.
G-code retains its existing ingestion path.

All workers in the server process share memory admission with other mesh
operations. The budget comes from `VAULT_MESH_MEMORY_BUDGET_FRACTION` and the
smallest detected host/container memory ceiling. Unknown memory capacity uses a
conservative scheduler budget. Disabling the existing triangle RAM cap does not
disable bounded prefetch.

The coordinator estimates each file's working memory before submitting it and
retains that reservation until publication consumes the result. It admits only
a bounded window of files, so a slow writer stops additional computation.
Unknown mesh costs and STEP reserve the whole budget. A large mesh waits for
smaller active jobs instead of losing its preview merely because more import
workers are configured. Reservations cover estimated parser/render memory and
retained output; they are not a hard RSS guarantee. Costs vary by format and
scene structure. The policy uses memory ceilings rather than continuously
tracking free RAM used by unrelated services, so administrators should leave
headroom through the budget fraction.

Workers return geometry and encoded thumbnails. Model resolution, deduplication,
versions, collections, storage publication and durable job states remain on the
ordered ingestion path. A failed file is reported through that same path, and
outstanding workers drain before their reservations are released. Rust performs
the native mesh operations; scheduling and persistence remain in Python.

Compare the complete archive with the same rendering settings:

```bash
uv run python scripts/bench_import.py /path/library.zip --workers 1 --output serial.json
uv run python scripts/bench_import.py /path/library.zip --workers 2 --output two.json --compare serial.json
uv run python scripts/bench_import.py /path/library.zip --workers 4 --output four.json --compare serial.json
uv run python scripts/bench_import.py /path/library.zip --workers 0 --output auto.json --compare serial.json
```

The report records requested and effective worker counts. Repeat runs before
choosing a setting: more workers can increase CPU work and memory use without
reducing elapsed time. This change does not remove archive entry/size limits or
replace the existing extraction of selected entries before ingestion.
