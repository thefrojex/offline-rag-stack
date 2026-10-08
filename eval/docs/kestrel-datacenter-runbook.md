# Kestrel Data Center Runbook

Kestrel is a fictional facility written for this repository's test set. Nothing here describes a real site.

## Backups

A full backup of the production database runs every Sunday at 01:00 UTC. Incremental backups run every night at 02:30 UTC. Backups are kept for 35 days and are copied to the Tern site, which is the disaster recovery location. A restore test is run on the first Monday of every month.

## Database failover

Declare an incident when replication lag on the primary database stays above 90 seconds for 5 minutes. To fail over, the on-call engineer promotes the replica at the Tern site with the command `kctl promote --site tern`. The target recovery time is 20 minutes. After promotion, update the status page and notify the customer support lead.

## On-call rotation

The on-call rotation is weekly and the handover happens on Tuesdays at 10:00 UTC. If the primary on-call engineer does not acknowledge a page within 10 minutes, the page escalates to the secondary engineer. Engineers must keep their pager devices charged and test them before each handover.

## Power and cooling

If utility power is lost, the UPS carries the full load for 12 minutes while the diesel generator starts automatically. The generator fuel tank is sized for 48 hours of continuous running. The cold aisle temperature alert fires at 27 degrees Celsius. At 32 degrees Celsius the on-call engineer must begin shutting down non-critical batch workloads.

## Access

Visitors must be escorted at all times and must sign the access log at the front desk. Badge access to the cage area is reviewed every quarter by the security lead.
