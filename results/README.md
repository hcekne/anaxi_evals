# Experiment evidence

There are no benchmark results in the initial repository release. Passing repository
validation means the specifications and prompt tooling are internally consistent;
it does not mean the benchmark has run or a treatment has won.

For each authorized campaign, keep a sanitized report in a uniquely named directory
such as `results/<date>-<experiment-id>/`. Include the completed
[experiment record](../templates/experiment.md), exact suite/runner/source commits,
content hashes, attempted-run counts, measurements, and stable references to raw
evidence. Keep machine-readable summaries alongside prose when the runner exists.

Store large artifacts, candidate repositories, raw transcripts, private source,
credentials, user data, and held-out cases in the authorized external experiment
store. Do not commit them here. A storage reference must include enough identity
and integrity information to retrieve and verify the evidence; it must not expose
secrets or make private evidence public. Use small synthetic examples when explaining
formats and label them as examples.

Preserve completed reports. Add a dated correction or superseding report with a
link to the original instead of silently changing results. Report every attempted
trajectory, repair, exclusion, and cost. `null` means unmeasured; zero is a measured
value. Separate infrastructure-invalid runs, functional failures, and inconclusive
comparisons. Never mix modeled timing with measured timing.

Published scenario templates are development material. This repository is not a
secure place to store unseen confirmation cases, expected answers, or private probe
instances when benchmark subjects or tool developers can read it.
