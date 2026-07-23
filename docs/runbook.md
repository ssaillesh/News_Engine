# Operations Runbook

> **Phase 1 stub.** Collection is not implemented yet, so most operational
> procedures below are placeholders to be filled in as later phases land
> (DESIGN.md §16). What exists today is configuration + CLI introspection.

## Current capabilities

```bash
archiver version    # package version
archiver config     # resolved configuration (secrets masked)
archiver doctor     # validate configuration loads and is consistent
```

## Configuration

- Precedence: env vars > `.env` > profile YAML (`src/archiver/config/profiles/`) > defaults.
- Choose a profile with `ARCHIVER_ENV` (`dev` | `test` | `prod`).
- Compliance switches and their meaning: see [ADR-0003](adr/0003-conservative-compliance-defaults.md).
- Never commit a real `.env`; secrets are scrubbed from all logs.

## To be written (later phases)

- [ ] Start / stop / restart the service (Phase 6, 10)
- [ ] Resume after downtime & checkpoint inspection (Phase 6)
- [ ] Draining and reprocessing the dead-letter queue (Phase 6)
- [ ] Backup & restore drill (Phase 10)
- [ ] Responding to a DEGRADED (blocked) target (Phase 6–7)
- [ ] Frontier-lag alert response (Phase 7)
- [ ] Reprocessing raw payloads after a parser fix (Phase 4–5)
