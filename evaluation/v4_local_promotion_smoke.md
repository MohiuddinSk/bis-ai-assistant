# Local V4 promotion smoke

The separate port-8001 V4 container started with explicit V4 selection and reached `ready` / 1,160. Its deterministic API smoke passed 22/22. The separate V3 rollback container reached `ready` / 917 and returned a grounded battery-toy answer. Restarting V4 restored `ready` / 1,160 and a safe Form V limitation.

Post-configuration full backend discovery passed: 491 tests, `OK (skipped=1)`.
