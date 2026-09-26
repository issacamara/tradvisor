# Isolated Restore Drill Runbook

This runbook is for an approved development-only drill. It is not authorization to provision, restore, mutate production, seed data, or activate schedules.

1. Obtain separate owner approval for an isolated target and record the target, operator, start time, and expected cost ceiling.
2. Capture the backup point and isolate the target from active clients, workers, schedules, and admission changes.
3. Restore into the isolated target only. Reconcile with the recovery register before allowing reads.
4. Verify old recovery IDs, pending orders, revoked users, reset generations, and restored copies cannot mutate or resurrect active state.
5. Reject or fence pending orders from the old recovery; record the count and released reservations.
6. Record elapsed recovery duration and the potential loss represented by the backup point.
7. Keep the isolated target blocked after the drill and destroy it only under the approved cleanup procedure.
