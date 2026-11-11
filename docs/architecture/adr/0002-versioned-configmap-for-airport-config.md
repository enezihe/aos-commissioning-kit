# ADR 0002: Store the airport config as versioned ConfigMaps

- **Status:** Accepted
- **Date:** 2026-11-11

## Context
The airport file is customer data: terminals, gates, carousels and airlines. The flight service checks
every gate against it. A wrong upload leaves the system in an unknown state unless the previous
version can be restored quickly.

## Decision
`aos-config upload` stores every upload twice in the same namespace:
- `airport-config`: the live copy the service mounts, labelled with its version number.
- `airport-config-vN`: an archive copy of that version, never deleted.

A rollback copies an archived version back into `airport-config`. Uploads are a dry run unless
`--apply` is given, and the file is validated before it reaches the cluster.

## Alternatives considered
- **Edit the ConfigMap in place with kubectl:** no history; a mistake cannot be undone except from memory.
- **Keep the config in the image:** every data change needs a rebuild and a redeploy, and the customer
  data is mixed with code.
- **Store versions in Git only:** good for review, but the cluster does not know which version it runs;
  the label on the live ConfigMap answers that.

## Consequences
- Any version can be restored with one command, and the live version is visible on the cluster.
- Archive ConfigMaps accumulate; there is no cleanup yet.
- The service reloads the mounted file when it changes, so an upload or a rollback takes effect without a restart (after Kubernetes refreshes the mounted file).
