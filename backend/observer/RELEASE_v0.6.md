# Observer v0.6 unified baseline

Status: BUILT_VALIDATED_NOT_LIVE

Artifact:
- Drive file: grid_pilot26_android_observer_v0.6_unified_20260919.zip
- Drive ID: 1CBv0NZZ4BzXGUx-KjGockMGSVnp--Q4f
- SHA-256: ed07ccfe289279039eaa6cc76caf62c0029207372dd183841efe9e730fe5cb2a

Version lineage consolidated:
- collector/core v0.4
- runtime supervision/hardening package v0.5
- fail-closed fresh snapshot upload fix v0.5.1

Unified release rule:
- package version = observerVersion = 0.6
- no split core/runtime version label from v0.6 onward

Safety:
- READ_ONLY
- AUTO_EXECUTION_OFF
- no trading behavior added

Validation completed:
- Python bytecode compile passed
- bash syntax checks passed for all shell scripts
- ZIP integrity test passed
- archive manifest regenerated

Deployment state:
- The v0.6 package has NOT yet replaced the live Redmi runtime.
- Until an explicit install + fresh live readback proves observerVersion=0.6, the current live producer remains whatever the latest.json self-identifies.
