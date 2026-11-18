# Shared publication pilot — draft, not deployed

This lot adds a shared add-fight transaction, runner, isolated CI and a manual PFL
pilot reaching public verification and a replay check. Existing UFC functions,
collectors, daily workflows and public JavaScript are not replaced.

The database policy starts disabled. Preview never writes agenda tables. The pilot
collects and writes the journal even when publish=false; this is not a zero-write run.
Only PFL is configured initially. Future adapters must provide the trusted report
shape and journal provenance required by the shared writer.

Locally checked: Python compilation, five runner tests, JavaScript syntax.
Not yet checked: PostgreSQL execution, full repository test suites, public rendering,
concurrency and forced rollback after an audit failure. Production readiness is NOT claimed.
The temporary test schema must NEVER be run against production.

Required order:
1. Commit on feat/shared-publication-loop and run isolated CI.
2. Resolve failures and add concurrency and forced-rollback coverage.
3. Review against a nonproduction copy of the real schema and privileges.
4. Approve merge and production migration separately; policy remains disabled.
5. Configure PUBLIC_SITE_URL with the actual deployed HTTPS URL.
6. Run publish=false and inspect per-event previews and review reasons.
7. Only with explicit approval, enable the PFL policy and run publish=true.
   This may publish ALL eligible PFL events in the run, not only Lyon.
8. Confirm real public verification and replay without additional writes.

A browser failure does not undo an already committed publication. Inspect receipts
before retrying. Prior payload and evidence are retained as prepublication_state.
The journal's auto_publishable=false constraint is preserved: the writer revalidates
fresh persisted evidence rather than trusting that Boolean or an old card position.

No scheduling, creation of new events, source/date fallback policies, opponent changes,
deletions, fallback regeneration or compensation after publication are activated here.
Existing daily continue-on-error steps remain unchanged; this pilot does not use them.
The old create-event guardrail stage is bypassed, not reused with an invalid baseline.
The old public PFL summary RPC still needs its source_report filter updated separately.
The pilot is a first end-to-end add-fight slice, not the complete future automation.
