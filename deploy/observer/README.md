# Observer v0.6 VPS deployment

Status: PREPARED_NOT_DEPLOYED.

The deployment is shadow-only. The Redmi/Termux contour remains untouched and acts as the legacy/rollback source during migration.

Planned VPS path:
`/opt/crypto-control/backend/observer/runtime`

Canonical source bundle:
`backend/observer/releases/grid_pilot26_android_observer_v0.6_unified_20260919.zip`

Deployment sequence:
1. checkout `vps-foundation`;
2. extract the v0.6 bundle into the runtime directory;
3. create a Python virtual environment and install `backend/observer/requirements.txt`;
4. provide READ_ONLY credentials outside Git;
5. install the systemd service and timer;
6. run `ops/observer_vps_smoke_check.sh`;
7. compare VPS snapshots with the legacy contour;
8. promote only after shadow comparison is closed.

No exchange-write capability is introduced.
