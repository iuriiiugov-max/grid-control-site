# CRYPTO CONTROL architecture

Target model:

1. Git repository = desired-state source of truth for code/config/schemas.
2. VPS backend = always-on execution and orchestration.
3. PostgreSQL = operational state, history and audit.
4. Live exchange API = current exchange reality.
5. Main chat = human control/architecture/audit interface.
6. Telegram = operational UI.
7. Reconciliation continuously compares expected vs loaded/runtime state.

Current phase remains READ_ONLY / AUTO_EXECUTION_OFF.
