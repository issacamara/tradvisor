# Release manifest

`manifest.py` creates the public, deterministic release record used by the V1
delivery handoff. It records the full source commit, immutable backend and FI-1
job image digests, SHA-256 checksums for function archives and both environment-specific
function archives, rule versions, and SHA-256 fingerprints of environment
configuration. Environment-specific frontend artifacts are built by each
delivery workflow after its API URL is available, rather than being bundled in
the shared release. It does not record configuration values or credentials.
Schema version 2 adds the required immutable FI-1 job image digest.

The FI-1 image contains the bounded job command and its locked ingestion
dependencies. Development delivery resolves `fi1_job.digest` to the
environment-local Artifact Registry image; later promotion carries that same
digest between registries. Runtime values and credentials remain environment
configuration, outside the image and manifest.

The command fails closed for mutable image tags, short commits, missing
duplicate metadata keys, missing rule versions, malformed fingerprints, and
archives without the matching embedded target marker. Toolchain versions are
included as provenance. The backend digest argument is `sha256:<digest>` rather
than an image tag.
