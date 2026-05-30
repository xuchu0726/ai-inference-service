# RunPod Network Volume Recovery Archive - 2026-05-27

This archive preserves a compact recovery record from the old RunPod Network Volume before the volume was released.

Archive file:

- `artifacts/archive/runpod_network_volume_recovery_20260527.tar.gz`

The archived records include:

1. Environment bootstrap probe from the recovered volume.
2. CPU Pod volume mount check.
3. GPU memory residue diagnostics.
4. Pod restart, stop-start, ready-check, and new-pod GPU memory checks.
5. Recovered volume status snapshot.
6. Old backup missing-file list.
7. A README explaining what was preserved and what was excluded.

The archive intentionally excludes large or reproducible directories such as Hugging Face cache, Python virtual environments, installable tools, temporary clean clones, and duplicated repository snapshots.

This archive is not part of the main Week2 experimental result set. It is retained as infrastructure recovery evidence and as a reference for future cloud GPU troubleshooting.
