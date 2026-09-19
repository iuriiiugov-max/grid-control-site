# Observer v0.6.1 — VPS shadow release

Status: PROMOTED_NOT_STARTED

Runtime mode:
READ_ONLY_GET_ONLY_PROXY_OPTIONAL

Changes from v0.6:
- proxy_url is optional
- absent proxy_url => direct connection
- present proxy_url remains permission-checked and strictly validated
- trust_env remains false
- GET-only guard unchanged
- ALLOWED_GET_PATHS unchanged
- FORBIDDEN_WRITE_MARKERS unchanged
- auth/signing unchanged

Validation:
- Python compile PASS
- built-in self-test PASS
- proxy regression tests 5/5 PASS

Runtime collector SHA256:
17ef8d4fc9576888d66ccf7ed247697bc5e4844814bf3e1d22c4c56fe416df87

Safety:
- READ_ONLY
- AUTO_EXECUTION_OFF
- no trade/write capability added
- credentials not committed
- secrets forbidden in Git
