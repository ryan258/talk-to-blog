# State Management

- **Global State Prohibition:** Completely forbidden. No module-level mutable variables permitted.
- **Orthogonal Data Execution:** Operation execution must remain inherently stateless. Component behavior must rely exclusively on explicit arguments.
- **Data Mutability Constraint:** Input strings are immutable. Operations must return new transformed strings (e.g., regex substitutions).
- **Execution Context:** Internal memory accumulation (e.g., `current_chunk`) strictly confined to local function scope within loops.
- **Deterministic Passing:** Cross-boundary context (such as current date) must be resolved dynamically but passed explicitly.
