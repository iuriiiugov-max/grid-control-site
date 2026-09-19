# Observer v0.6 — VPS shadow deployment

Status: PREPARED_NOT_DEPLOYED

The Redmi/Termux Observer remains the production/rollback contour. The VPS copy runs in parallel and must not replace it until shadow comparison is closed.

## Runtime
- Linux VPS
- Python virtualenv
- systemd service + timer
- READ_ONLY Bitget credentials only
- AUTO_EXECUTION_OFF
- no trade/withdraw/transfer credentials
- no secrets in Git

## Secret directory
The collector reads `GRID_PILOT26_SECRET_DIR`. On VPS the planned directory is:

`/etc/crypto-control/observer-secrets`

Required files, mode 0600:
- grid_pilot26_READ_api_key
- grid_pilot26_READ_passphrase
- grid_pilot26_READ_private.pem
- proxy_url

## Shadow acceptance gate
Do not promote VPS Observer until:
1. `observerVersion == "0.6"`
2. fresh snapshots survive restart/reboot tests
3. account/private-state semantics match the legacy contour
4. known BGB bot detail is represented correctly
5. TTL/fail-closed behavior matches
6. no exchange write paths are possible
7. discrepancies are explained and recorded
