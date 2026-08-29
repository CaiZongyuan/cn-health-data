# Data Rights

Repository-owned software code and original project documentation use the MIT
License. Source-data rights are independent: the project does not own or claim
ownership of third-party healthcare data, and the MIT License does not apply to
raw data or generated record-level data artifacts by default.

Local builds and public distribution are separate workflows. A Dataset Contract
can describe a local Candidate with `review-required`; the signed Registry accepts
only Releases whose metadata records the applicable basis, evidence, attribution,
reviewed-by/date, allowed artifact types, and `releaseEligible: true`.

Supported distribution states are `public`, `normalized-only`, `metadata-only`,
`private`, and `review-required`. These values describe artifact handling; they
do not change the source terms or grant additional rights.

Every releasable artifact must identify its source, legal basis, attribution,
and allowed artifact type. A code license cannot be used as evidence that a
third-party dataset may be redistributed.
