# Change Spec Design (Template)

## Current Behavior Reference
- Primary audit: `SYSTEM_BEHAVIOR_AUDIT.md`
- Short snapshot: `spec/system_change_template/CURRENT_STATE.md`

## Proposed Design
- **Goal:** <describe what changes>
- **Components impacted:** <signal_engine / dispatcher / position_manager / trade_stream / DB>
- **Data model changes:** <tables, columns, views>
- **Risk controls:** <gates/limits>
- **Observability:** <new logs/metrics>
- **Rollback plan:** <how to revert safely>

## Notes
Keep the design aligned with the existing end‑to‑end flow unless explicitly changing it:
```
RSS -> classify -> telemetry -> features -> watchlist -> signal -> dispatcher -> execution -> position manager
```

