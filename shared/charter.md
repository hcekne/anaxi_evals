# Engineering charter

Deliver the requested behavior and preserve working behavior. Before editing,
find the existing owner of the responsibility and the contracts it participates in.

Keep unrelated responsibilities separate. Prefer the smallest design that makes
the current change and plausible next changes easy. Reuse an existing extension
point; introduce an abstraction when real variation justifies it. Keep integration
protocols and vendor-specific behavior at the edge. Represent capability and error
differences honestly. Do not add services, factories or frameworks for their own sake.

Keep public interfaces explicit and compatible. Consider stored data, events,
configuration, authorization and runtime registration as well as imports.

Make meaningful parts independently buildable and testable where practical.
Select checks from the actual change impact; broaden them when impact is uncertain.
Never suppress a necessary check to make CI faster. Preserve independent release
options where contracts allow them, and verify compatibility with deployed versions.

Use tests to protect behavior and boundaries. Keep changes reviewable. Record the
checks performed, unresolved risks and any deliberate tradeoff. Remove obsolete
code when replacing a feature, without discarding supported behavior or data.
