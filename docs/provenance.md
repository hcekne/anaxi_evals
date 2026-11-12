# Import provenance

Suite 0.1.0 packages the three specifications authored on 12 November 2026 in the owner's authorized floThink workspace. The repository is the working source for future eval development; the workspace retains the original design notes and a pointer here. Internal architecture/product notes were not copied into this repository.

The original prompt queue was recovered from its authorized Storage reference and verified against its recorded SHA-256. Every scenario ID, title, step and user prompt matches the original queue. Its initial bytes are unchanged:

```text
requests.jsonl
6b14f2238528b11c0e3d369c4e70c28e18d53d815262455180fd7b744c76dd43
```

Original Markdown hashes, **before** portable-link edits:

| Original document | Repository destination | SHA-256 of original |
| --- | --- | --- |
| Eval 1 - RelayDesk.md | [evals/relaydesk/spec.md](../evals/relaydesk/spec.md) | `9de87a3c41f2bd10cd680dfd8c382bc6cb508b756d287201970e6de523f5a843` |
| Eval 2 - DispatchLedger.md | [evals/dispatchledger/spec.md](../evals/dispatchledger/spec.md) | `ec839bce9ef6b0ebd7653b474c6eaa605bd63440831a1cfd035673db0395af72` |
| Eval 3 - CaseFlow.md | [evals/caseflow/spec.md](../evals/caseflow/spec.md) | `8e0a3a84c2c251614a01b8362cf03766a8a2bc63f051b3bcd035e1b11ea1b939` |
| AnaxiGraph Eval Suite - Protocol.md | [docs/protocol.md](protocol.md) | `7585bcd50e32657dce37996923c089e1a69ef045b101d07430b0121a820ebd72` |

Porting changes replace workspace wiki links with relative Markdown links, route the combined queue to the repository root, generalize session-specific source-access and prior-run references, and use suite version `0.1.0` in the illustrative record. The protocol's shipped-versus-intended capability discussion reflects the original design notes; operators must discover and freeze the actual sidecar build used in a campaign. No new AnaxiGraph capability is asserted here.

The shared charter was extracted verbatim from the protocol. Retrieval tools, catalog, contribution guidance, templates and a package CI template were added for repository use. The CI workflow is not active because the connected app cannot write workflows. Experimental prompts, acceptance criteria and measurement rules were preserved. Future changes are tracked in [CHANGELOG.md](../CHANGELOG.md) and Git history; this import record is historical, not a checksum assertion about later versions.
