# Architecture Quality

Use this document when creating modules, refactoring responsibilities, introducing adapters, or reviewing whether a design will remain maintainable.

## Target State

A maintainable system has these properties:

- each business meaning has one clear owner
- each component has a narrow reason to change
- component boundaries are explicit contracts, not directory names alone
- dependencies flow in a deliberate direction
- external systems and storage formats do not define domain behavior
- changes remain local and their impact is predictable
- failures cross boundaries only through defined failure contracts
- tests protect both behavior and architecture
- abstractions reduce verified duplication or clarify a real boundary
- operational behavior can be observed, diagnosed, and recovered

The objective is not the maximum number of files, layers, interfaces, or services. The objective is controlled ownership of behavior and controlled propagation of change and failure.

## Core Rule: One Meaning, One Owner

A business rule, state transition, fallback order, calculation, validation policy, or presentation meaning must have one authoritative owner.

Do not implement the same meaning independently in:

- multiple database backends
- command-line and web entrypoints
- background jobs and request handlers
- adapters and domain modules
- compatibility wrappers and current implementations
- tests as copied production logic

Adapters may translate data. They must not redefine the meaning of that data.

Entrypoints may coordinate work. They must not become alternative policy owners.

Compatibility layers may preserve an old contract. They must delegate to the current owner instead of maintaining a second implementation.

## Responsibility Definition

For every non-trivial component, be able to state:

1. what it owns
2. what it explicitly does not own
3. its accepted inputs
4. its produced outputs
5. its invariants
6. its failure contract
7. the dependencies it may use
8. the state it may mutate

A component whose responsibility cannot be described in one or two precise sentences probably owns too much or is named too vaguely.

Prefer names that describe responsibility or domain meaning. Avoid using `manager`, `helper`, `service`, `utils`, or `common` as substitutes for a real ownership decision.

## High Cohesion and Low Coupling

Keep code together when it changes for the same reason.

Separate code when it changes for different reasons, such as:

- domain policy versus persistence
- state transition versus device communication
- repository mapping versus view-model assembly
- calculation versus formatting
- orchestration versus decision logic
- configuration loading versus business rules
- retry policy versus the operation being retried

Low coupling does not mean no collaboration. It means collaboration occurs through small, explicit contracts rather than knowledge of another component's internals.

## Boundary Contract

A boundary should define:

- semantic input and output types
- units and time basis
- nullability and missing-data behavior
- validation responsibility
- error categories
- retryability
- idempotency expectations
- ordering requirements
- compatibility and version expectations

Do not pass broad dictionaries, database rows, environment objects, or framework request objects deep into domain logic when a smaller typed model can express the real contract.

Do not hide failures as empty collections, zero values, or successful results unless that fallback is an explicit domain rule.

## Dependency Direction

Prefer this direction:

    entrypoint
        -> use case or orchestrator
        -> domain policy and domain models
        <- ports or interfaces
        <- external adapters

Inner domain modules must not import concrete databases, web frameworks, cloud SDKs, device drivers, environment readers, or presentation modules.

Outer modules adapt external details to inner contracts.

Composition roots may construct concrete implementations. Other modules should depend on the required capability rather than constructing infrastructure directly.

## Architecture Enforcement

Documented dependency rules are not enough. Enforce important rules automatically where practical.

Examples:

- domain packages must not import infrastructure packages
- repositories must not import presentation code
- adapters must not call each other directly
- concrete adapters may be created only in approved composition roots
- compatibility modules must delegate to the current owner
- forbidden cyclic dependencies must fail CI
- duplicate domain-policy implementations must be detected by review or focused tests

Use import analysis, architecture tests, lint rules, package boundaries, or small custom checks appropriate to the language and repository.

## State Ownership

Every mutable state must have an identifiable owner.

Define:

- who may write it
- who may read it
- whether concurrent writers are allowed
- how conflicts are detected
- how stale state is identified
- how partial updates are prevented
- how retries avoid duplicate effects

Prefer immutable values and explicit state transitions. Avoid shared mutable globals and broad context objects.

When concurrent or repeated execution is possible, consider:

- locks
- optimistic version checks
- transactions
- idempotency keys
- compare-and-swap
- single-writer design
- durable state-machine transitions

## Change Locality

A healthy architecture makes the expected change location predictable.

For every significant requirement change, ask:

- which component owns this decision
- how many production files must change
- whether another backend or entrypoint contains a copy
- whether external data formats leak into the change
- whether unrelated modules must be read to understand the impact
- whether tests can verify the change without constructing the whole system

A change that repeatedly requires edits across unrelated adapters, runners, and presentation modules indicates distributed ownership.

## Failure Containment

Code boundaries and runtime failure boundaries are different.

Logical containment requires:

- input validation at boundaries
- explicit error conversion
- limited shared state
- transactional writes
- bounded retries
- timeouts
- cancellation handling
- deterministic fallback ownership
- clear partial-success rules

Stronger runtime containment may require:

- separate processes
- worker isolation
- queues
- bulkheads
- circuit breakers
- resource limits
- independent health checks

Choose the isolation level according to failure cost. Do not introduce distributed services merely to imitate modularity.

## Observability

Each important operation should make it possible to reconstruct:

- which input or input summary was used
- which decision owner produced the result
- which external effects were attempted
- which fallback or retry path ran
- why an operation stopped or failed
- how long each relevant phase took
- which run, request, job, or device interaction the records belong to

Prefer structured logs, stable reason codes, correlation identifiers, and metrics over free-form messages alone.

Do not log secrets, credentials, sensitive payloads, or unbounded raw data.

## Compatibility and Migration

Contract preservation must be explicit.

Define:

- which fields, units, formats, and behaviors are public
- which changes are breaking
- how old and new implementations are compared
- whether dual run or shadow execution is needed
- schema and data migration order
- rollback conditions
- compatibility-wrapper removal conditions
- deprecation period and ownership

A compatibility wrapper is temporary architecture debt. Record its owner and deletion gate.

## Performance and Resource Contracts

A structurally clean refactor can still be harmful if it multiplies database reads, network calls, allocations, or conversions.

For critical paths, record relevant limits such as:

- maximum external calls
- query count
- batch size
- execution time
- memory use
- retry budget
- timeout
- data volume assumptions

Compare before and after when the refactor changes call structure or data movement.

## Security Boundaries

Treat external input and privilege changes as boundary concerns.

- validate untrusted data before domain use
- keep secrets and credentials outside domain models
- use least privilege
- do not log secrets
- keep authentication and authorization decisions explicit
- distinguish authentication failure, authorization failure, validation failure, and infrastructure failure
- do not let convenience adapters bypass security policy

## Testing Strategy

Protect two dimensions separately.

### Behavior evidence

- characterization tests for current behavior
- focused unit tests for domain rules
- boundary and error cases
- backend parity where several adapters implement one capability
- old-versus-new comparison during refactoring
- failure-injection tests for important external dependencies

### Architecture evidence

- allowed and forbidden dependency tests
- ownership map review
- no duplicate policy owner
- no bypass path around the approved owner
- no infrastructure imports in domain modules
- no compatibility path with an independent implementation
- no new broad context or generic utility layer hiding responsibility

Green behavioral tests do not prove that ownership improved. A clean directory layout does not prove that behavior was preserved. Require both kinds of evidence.

## Refactor Decision Gate

Before changing structure, answer:

1. What verified problem requires this change?
2. Which responsibility currently has multiple owners or no clear owner?
3. What is the intended final owner?
4. What behavior and compatibility contracts must not change?
5. What new boundary is introduced?
6. What dependencies become forbidden?
7. What failure modes remain and how are they contained?
8. What evidence will prove both behavior preservation and ownership improvement?
9. What later work must not undo?
10. What rollback path exists?

Do not begin a large structural change when these answers are unknown.

## Local-Optimization Risks

Reject or question changes that:

- reduce line count without clarifying ownership
- split one large file into many mutually dependent files
- centralize unrelated behavior in a generic service or context object
- move duplicated code without creating one authoritative owner
- create an interface for a hypothetical future need only
- make one backend clean while leaving other backends as policy owners
- pass tests by weakening assertions or changing characterization fixtures
- add retries without one owner, a budget, and idempotency
- convert every failure into an empty result
- hide infrastructure details behind a wrapper while leaking the same details through models
- introduce services or processes without a justified runtime isolation need
- combine refactoring, behavior changes, formatting churn, and migration in one patch

## Review Checklist

A structural change is ready only when reviewers can answer yes to the relevant questions:

- Is the authoritative owner of each changed meaning identifiable?
- Are ownership and non-ownership both documented or evident?
- Are inputs, outputs, invariants, and failure behavior explicit?
- Is dependency direction clear and enforced where important?
- Are mutable state and transaction ownership clear?
- Can failure impact and recovery be described?
- Is the change local for the requirement it addresses?
- Are behavior and architecture validated separately?
- Are compatibility, migration, and rollback conditions known?
- Did the change avoid unnecessary abstraction and layer count?
- Can a future maintainer find the correct change location without reading the whole repository?

## Definition of Done

Architecture work is complete only when:

- current behavior is preserved or an approved behavior change is documented
- each affected business meaning has one owner
- obsolete duplicate owners and bypass paths are removed or explicitly time-bounded
- dependency direction is valid
- important boundary contracts are testable
- state, transaction, retry, and fallback ownership are clear
- failure propagation is bounded and observable
- migration and rollback risks are addressed
- documentation matches the implemented structure
- the final diff is focused and reviewable


