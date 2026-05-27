This directory preserves small top-level records recovered from the old RunPod Network Volume before releasing it.

Included:
- CPU Pod mount check
- GPU memory residue diagnostics
- Pod restart / stop-start / new pod failure evidence
- Recovered volume status snapshot
- Old backup missing-file list
- Bootstrap environment probe

Excluded:
- hf_cache: model cache, reproducible by re-downloading
- venvs: Python virtual environments, reproducible by reinstalling dependencies
- tools: installable tooling
- github_clean_ai_inference_service: temporary clean clone
- old_backup_check: duplicate repository snapshot, audited separately

A compact full repository snapshot from the old volume is preserved separately:
artifacts/ai_inference_service_full_20260525_from_old_volume.tar.gz
