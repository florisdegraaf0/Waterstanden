# AGENTS.md

## Purpose

This file defines how coding agents should work in this repository.

The project is a Python web application whose primary data source is one or more external APIs. Optimize for:

1. correctness;
2. clear architecture;
3. maintainability;
4. testability;
5. operational robustness;
6. small, reviewable changes.

Prefer simple, explicit solutions over clever abstractions.

Do not optimize only for making the immediate task pass. Changes should leave the codebase in a better or equally maintainable state.

---

# Working in This Repository

## Before making changes

Before editing code:

1. Inspect the relevant parts of the repository.
2. Read `README.md`, `pyproject.toml`, and other nearby documentation when relevant.
3. Look for existing implementations of similar functionality.
4. Identify the established architecture, naming conventions, and dependency patterns.
5. Check for more specific `AGENTS.md` files in subdirectories.
6. Understand the existing tests around the code being changed.

Do not assume the repository uses a particular framework, HTTP client, validation library, or dependency-management tool. Determine this from the repository first.

Follow existing conventions unless there is a strong reason to improve them.

When conventions conflict with this file, prefer:

1. explicit user instructions;
2. a more specific nested `AGENTS.md`;
3. established repository conventions;
4. this file.

---

# Change Strategy

Make the smallest coherent change that solves the problem.

Avoid:

* unrelated refactoring;
* speculative abstractions;
* changing public interfaces unnecessarily;
* replacing libraries without a clear requirement;
* broad formatting changes mixed with functional changes;
* adding infrastructure for hypothetical future requirements.

When refactoring is necessary to implement a feature cleanly, keep the refactor focused on the affected area.

Do not silently change behavior outside the requested scope.

Preserve backwards compatibility unless the task explicitly requires a breaking change.

---

# Architecture

Maintain a clear separation between:

```text
HTTP / UI layer
      |
      v
Application / service layer
      |
      v
Domain models and business rules
      |
      v
External API clients / repositories
      |
      v
External services
```

A typical structure may resemble:

```text
src/
    app/
        web/
            routes/
            dependencies/
            templates/
        services/
        domain/
        clients/
        schemas/
        config.py
        exceptions.py
        logging.py
tests/
    unit/
    integration/
```

Treat this as architectural guidance, not a requirement to reorganize an existing project.

Do not move files solely to match this example.

## Dependency direction

Dependencies should generally point inward.

Prefer:

```text
route -> service -> API client
```

over:

```text
route -> raw HTTP request
```

or:

```text
API client -> route
```

Business logic must not depend on HTTP request objects, templates, framework-specific globals, or transport-specific response objects.

External API details should not leak throughout the application.

---

# Web Layer

Routes, controllers, views, or handlers should be thin.

Their responsibilities are generally limited to:

* parsing input;
* invoking application services;
* mapping known errors to HTTP responses;
* selecting templates or response schemas;
* returning the result.

Do not place significant business logic in route handlers.

Avoid:

```python
@router.get("/items")
async def items():
    response = await client.get(EXTERNAL_URL)
    data = response.json()

    filtered = []
    for item in data:
        if item["active"] and item["score"] > 10:
            filtered.append(...)
    return filtered
```

Prefer:

```python
@router.get("/items")
async def items(service: ItemService = Depends(get_item_service)):
    return await service.get_active_items()
```

The service owns application behavior. The API client owns communication with the remote API.

---

# Service Layer

Use services for application use cases and orchestration.

Services may:

* combine data from multiple API calls;
* enforce business rules;
* transform domain data;
* coordinate caching or persistence;
* decide what should happen when dependencies return partial or missing data.

Services should not know unnecessary details about HTTP transport.

Prefer dependencies to be passed explicitly:

```python
class ItemService:
    def __init__(self, item_client: ItemClient) -> None:
        self._item_client = item_client
```

Avoid constructing infrastructure dependencies inside business logic:

```python
class ItemService:
    def __init__(self) -> None:
        self._client = httpx.AsyncClient(...)
```

Explicit dependencies make behavior easier to understand and test.

---

# External API Clients

All communication with an external API should be isolated behind a dedicated client, gateway, adapter, or repository abstraction.

Do not scatter raw HTTP requests throughout the application.

A client should own details such as:

* base URLs;
* endpoints;
* authentication headers;
* query parameters;
* serialization;
* response parsing;
* pagination;
* API-specific error interpretation;
* timeouts;
* retry behavior;
* rate-limit handling.

For example:

```python
class WeatherClient:
    async def get_forecast(self, location: str) -> Forecast:
        ...
```

Application code should prefer working with application/domain objects rather than arbitrary JSON dictionaries.

Avoid exposing a raw `httpx.Response`, `requests.Response`, or equivalent beyond the API integration layer.

---

# API Response Validation

Treat all external data as untrusted input.

Do not assume an API response is valid simply because the API normally returns a particular structure.

Validate data at the system boundary.

Prefer typed models for non-trivial API responses.

For example:

```python
class ApiItem(BaseModel):
    id: str
    name: str
    status: str
```

Convert external API models into domain or application models when the distinction is useful.

Avoid passing large nested `dict[str, Any]` structures throughout the codebase.

Do not over-model trivial responses, but use explicit types whenever doing so improves correctness.

---

# API Schema Boundaries

Keep external API schemas separate from internal domain concepts when they have different meanings or lifecycles.

For example:

```text
External API JSON
       |
       v
API response schema
       |
       v
mapping / normalization
       |
       v
domain model
       |
       v
application behavior
```

This boundary prevents API changes from propagating through the entire application.

Do not name internal concepts after awkward API field names purely to avoid writing a mapper.

Prefer an explicit transformation.

---

# HTTP Client Management

Reuse HTTP client instances where appropriate.

Do not create a new connection pool for every request.

Prefer application-scoped or dependency-managed clients.

Always configure explicit timeouts.

Never rely indefinitely on a library's default timeout behavior.

When using asynchronous frameworks, use an asynchronous HTTP client unless there is a concrete reason not to.

Do not call blocking network libraries directly from the async event loop.

---

# Retries and Resilience

Retries must be deliberate.

Do not blindly retry every failed request.

Generally consider retries for transient failures such as:

* connection errors;
* temporary DNS/network failures;
* HTTP `429`;
* selected HTTP `5xx` responses.

Avoid automatically retrying failures that are unlikely to succeed, such as most `4xx` responses.

Use bounded retries.

Prefer exponential backoff with jitter when the existing stack supports it.

Honor `Retry-After` when appropriate.

Be careful retrying non-idempotent operations.

Every remote request must eventually fail rather than retry indefinitely.

---

# Timeouts

External calls must have finite timeouts.

Consider separate timeout limits where supported:

* connection timeout;
* read timeout;
* write timeout;
* pool timeout.

Choose values appropriate to the application rather than using excessively large values to hide unreliable dependencies.

Timeout failures should be translated into meaningful application-level errors.

---

# Pagination

If an API paginates results, handle pagination explicitly.

Do not assume the first page contains all records.

Prefer an API such as:

```python
async for item in client.iter_items():
    ...
```

when callers normally need the complete result set.

Prevent accidental infinite pagination by validating cursors, page counts, or termination conditions.

Tests should cover multi-page responses when pagination is relevant.

---

# Rate Limits

Respect API rate limits.

Do not add unnecessary API calls inside loops when the same information can be retrieved in bulk.

Prefer:

```text
1 bulk request
```

over:

```text
1 request per item
```

when the API supports it.

If rate-limit information is available through response headers, keep its interpretation inside the API integration layer unless application behavior explicitly depends on it.

---

# Errors

Use meaningful application-specific exceptions.

For example:

```python
class ExternalServiceError(Exception):
    pass


class ExternalServiceUnavailable(ExternalServiceError):
    pass


class ExternalResourceNotFound(ExternalServiceError):
    pass
```

Do not make higher application layers interpret low-level networking exceptions everywhere.

Translate errors at architectural boundaries.

For example:

```text
httpx.TimeoutException
        |
        v
ExternalServiceUnavailable
        |
        v
HTTP 503
```

Do not catch `Exception` unless you genuinely intend to handle every possible exception at that boundary.

Never silently swallow unexpected exceptions.

---

# Partial Failure

When a page depends on several independent external requests, consider whether partial results are acceptable.

Make this behavior explicit.

Do not silently return incomplete data in a way that appears complete.

If degraded behavior is intended:

* make it predictable;
* log the dependency failure;
* expose an appropriate status to the caller or UI when useful;
* test the degraded path.

---

# Configuration

Configuration must be centralized.

Configuration may include:

* API base URLs;
* API keys;
* timeouts;
* feature flags;
* environment names;
* cache settings;
* logging configuration.

Prefer typed configuration objects when the project already supports them.

Do not access environment variables throughout arbitrary modules.

Prefer:

```python
settings.external_api_url
```

over repeated calls to:

```python
os.getenv("EXTERNAL_API_URL")
```

---

# Secrets

Never commit:

* API keys;
* passwords;
* private tokens;
* session secrets;
* credentials;
* production `.env` files.

Never log secrets.

Do not include credentials in exception messages or debugging output.

Provide placeholders in `.env.example` or equivalent documentation when configuration must be documented.

Example:

```dotenv
EXTERNAL_API_URL=https://api.example.com
EXTERNAL_API_KEY=
```

---

# Types

Use type annotations for public functions, service methods, API client interfaces, and important internal boundaries.

Prefer concrete types over `Any`.

Avoid unnecessary casts that merely silence the type checker.

If the type checker identifies a legitimate mismatch, fix the underlying design or data handling when practical.

Prefer:

```python
def find_item(item_id: str) -> Item | None:
    ...
```

over:

```python
def find_item(item_id):
    ...
```

Follow the Python version configured by the project.

Do not introduce syntax unsupported by the project's minimum Python version.

---

# Data Models

Use the right model for the right boundary.

Distinguish where useful between:

* external API schemas;
* request/response schemas;
* domain models;
* persistence models.

Do not create duplicate models without a meaningful boundary.

Conversely, do not force one model to represent unrelated concerns simply to avoid mapping code.

Keep transformations explicit and testable.

---

# Functions and Classes

Prefer small units with one clear responsibility.

A function should generally operate at one level of abstraction.

Avoid functions that simultaneously:

1. make an HTTP request;
2. parse JSON;
3. apply business rules;
4. mutate persistence;
5. build an HTTP response.

Split responsibilities at natural boundaries.

Prefer composition over deep inheritance hierarchies.

Introduce interfaces/protocols only when they provide practical value, such as multiple implementations or useful test seams.

Do not create an interface for every class by default.

---

# Naming

Use names that express intent.

Prefer:

```python
fetch_customer_orders()
```

over:

```python
get_data()
```

Prefer:

```python
is_customer_eligible
```

over:

```python
flag
```

Avoid abbreviations unless they are well established in the domain.

Use terminology consistently across routes, services, models, tests, and documentation.

---

# Comments and Documentation

Code should explain *what* through clear structure and naming.

Comments should primarily explain *why*.

Avoid comments that simply restate code:

```python
# Increment count
count += 1
```

Useful comments explain non-obvious constraints:

```python
# The upstream API occasionally returns duplicate records across page
# boundaries, so deduplicate by the stable external ID.
```

Document public behavior and important architectural decisions.

Do not add large docstrings to trivial functions merely for completeness.

---

# Logging

Use structured, actionable logging where supported by the project.

Log events such as:

* external service failures;
* retries;
* unexpected response formats;
* degraded behavior;
* important application state transitions.

Avoid noisy logs for normal control flow.

Do not log entire external API payloads by default.

Payloads may contain:

* personal information;
* credentials;
* tokens;
* unexpectedly large data.

Prefer useful metadata such as:

```text
service
endpoint
status_code
request_id
duration
attempt
```

Never log authentication credentials.

---

# Observability

When modifying important external API interactions, preserve or improve observability.

Where the project's tooling supports it, make it possible to answer:

* which dependency failed;
* which operation failed;
* how long the call took;
* how often it is failing;
* whether retries occurred.

Preserve upstream request IDs or correlation IDs where useful.

Do not add a new observability framework unless the task requires it.

---

# Caching

Introduce caching only when there is a demonstrated need.

When using caching, define:

* the cache key;
* TTL;
* invalidation behavior;
* behavior on cache failure;
* whether stale values may be served.

Do not cache error responses unless this behavior is deliberate.

Do not allow caching to silently change correctness semantics.

Keep caching outside core business logic where practical.

---

# Security

Treat browser input and external API data as untrusted.

Follow the web framework's established protections against:

* cross-site scripting;
* cross-site request forgery;
* injection;
* unsafe redirects;
* insecure cookie handling;
* path traversal.

Do not construct URLs, SQL, HTML, or shell commands through unsafe string concatenation.

Validate user-provided URLs before requesting them.

Be especially careful when implementing server-side requests to user-controlled destinations, as these may introduce SSRF vulnerabilities.

Do not disable TLS certificate verification to work around connectivity problems.

---

# Authentication and Authorization

Authentication answers:

> Who is this user?

Authorization answers:

> Is this user allowed to perform this action?

Do not treat authentication as authorization.

Enforce authorization server-side.

Never rely solely on hidden UI elements or client-side checks to protect sensitive operations.

Follow existing project mechanisms rather than introducing parallel authentication systems.

---

# Dependency Management

Use the dependency management tool already configured in the repository.

Do not add a dependency when the standard library or an existing dependency solves the problem cleanly.

Before adding a package:

1. confirm the functionality is not already available;
2. verify that the dependency is appropriate for the project;
3. add it through the project's normal dependency mechanism;
4. update the lockfile when applicable;
5. use the dependency directly rather than wrapping it in unnecessary abstractions.

Avoid introducing large frameworks for small features.

---

# Testing

Every meaningful behavior change should be covered by tests.

Tests should focus on observable behavior rather than implementation details.

Prefer a testing pyramid with many fast unit tests and a smaller number of integration tests.

## Unit tests

Unit tests should not make real external network requests.

Mock or fake the API boundary.

Prefer testing application code through a client abstraction rather than mocking deep internals of an HTTP library.

For example:

```python
class FakeItemClient:
    async def get_item(self, item_id: str) -> Item:
        return Item(id=item_id, name="Example")
```

This is usually preferable to mocking several internal `httpx` methods from a service test.

## API client tests

Test API clients separately.

Cover important cases such as:

* successful responses;
* malformed payloads;
* missing fields;
* authentication failures;
* `404` responses;
* rate limiting;
* server errors;
* timeouts;
* pagination;
* retry behavior when applicable.

Use mocked HTTP responses or the project's established HTTP test tooling.

## Web tests

Test important web behavior from the HTTP boundary when practical.

Cover:

* status codes;
* response schemas;
* validation;
* error mapping;
* authentication and authorization where relevant.

Do not test framework behavior already guaranteed by the framework unless project-specific behavior depends on it.

---

# Test Quality

Tests must be:

* deterministic;
* isolated;
* reasonably fast;
* independent of execution order.

Avoid:

* real network access in unit tests;
* arbitrary sleeps;
* dependencies on the current date without controlling time;
* dependencies on developer-specific files;
* tests that succeed only when run after another test.

Use fixtures and factories to make test setup clear.

Prefer realistic API fixtures but keep them as small as possible.

---

# Bug Fixes

For a bug fix:

1. understand the root cause;
2. add or adjust a test that reproduces the bug;
3. implement the smallest robust fix;
4. verify the regression test passes;
5. run related tests.

Do not merely patch the visible symptom if the underlying invariant can be fixed clearly.

---

# Async Code

When the application is asynchronous:

* avoid blocking I/O in the event loop;
* await asynchronous operations correctly;
* use concurrent requests only when they are genuinely independent;
* bound concurrency when talking to external systems;
* avoid spawning untracked background tasks.

Prefer structured concurrency where available.

Do not use concurrency simply to make code appear faster.

When making multiple independent external calls concurrently, preserve understandable error behavior.

---

# Performance

Optimize only where the behavior or architecture reasonably requires it.

Watch especially for:

* network calls inside loops;
* duplicate requests for the same resource;
* sequential requests that could safely execute concurrently;
* fetching substantially more API data than necessary;
* repeated parsing or transformation of large payloads.

Network round trips usually matter more than minor Python micro-optimizations in API-driven applications.

Prefer readable code until measurements show otherwise.

---

# Dates and Time

Use timezone-aware datetimes.

Prefer UTC internally unless the domain requires otherwise.

Convert into user-facing time zones at presentation boundaries.

Do not rely on the machine's implicit local timezone.

When testing time-dependent behavior, freeze or inject time rather than relying on the current clock.

---

# Formatting and Code Quality

Use the formatters, linters, and type checkers configured by the repository.

Common examples may include:

```bash
ruff check .
ruff format --check .
mypy src
pytest
```

or their equivalents through the project's package manager:

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest
```

These commands are examples only.

Inspect `pyproject.toml`, CI configuration, `Makefile`, `justfile`, or repository documentation to determine the actual commands.

Do not introduce competing formatting or linting tools when equivalents are already configured.

---

# Validation Before Completion

After making changes, run the narrowest useful checks first.

For example:

```text
affected test
    ↓
affected test module
    ↓
related test suite
    ↓
lint / formatting / typing
    ↓
full suite when appropriate
```

Before considering a task complete, make a best effort to run all repository checks relevant to the changed code.

If the repository defines a standard validation command such as:

```bash
make check
```

or:

```bash
just check
```

prefer it.

Do not claim a check passed unless it was actually run successfully.

If a check cannot be run, clearly state:

* which check was not run;
* why;
* what was validated instead.

---

# Existing Failures

Do not hide or silently fix unrelated existing failures.

If validation reveals a pre-existing problem unrelated to the requested change, distinguish it from failures introduced by the current work.

Only fix unrelated failures when the user explicitly asks or when the fix is necessary for the requested work.

---

# Migrations and Persistent Data

Do not assume the application has a database.

If persistent storage exists, follow its established migration system.

Never modify a production schema manually when migrations are expected.

Avoid destructive migrations unless explicitly required.

For risky data transformations, prefer changes that are reversible or safely staged.

---

# Public Interfaces

Treat these as public interfaces when applicable:

* HTTP routes;
* response schemas;
* CLI commands;
* environment-variable names;
* configuration fields;
* exported Python functions;
* persisted data formats.

Do not change them casually.

If a public interface must change, update:

* implementation;
* tests;
* documentation;
* callers;
* migration or compatibility behavior where relevant.

---

# Frontend and Templates

If the application includes server-rendered templates or frontend assets, keep presentation concerns separate from business logic.

Do not duplicate domain rules in templates or JavaScript if the server is authoritative.

Templates should render prepared data rather than perform complex transformation logic.

Maintain established accessibility practices.

Do not introduce a frontend framework solely for a small UI change.

---

# Documentation

Update documentation when a change affects how developers or operators use the project.

Examples include:

* new environment variables;
* changed setup steps;
* new API integrations;
* changed commands;
* new architectural constraints;
* changed public endpoints.

Keep documentation close to the source of truth.

Do not duplicate large amounts of information across multiple documents.

---

# New Features

When implementing a new feature, prefer this sequence:

```text
understand existing behavior
        ↓
define domain/application behavior
        ↓
define external API boundary
        ↓
implement client/integration
        ↓
implement service/use case
        ↓
connect web layer
        ↓
add tests
        ↓
run validation
```

Do not start by putting all new behavior into a route and defer architecture until later.

---

# Refactoring

Refactor when it makes the requested change safer or substantially clearer.

Good reasons include:

* duplicated business rules;
* HTTP calls leaking through several layers;
* a function having several unrelated responsibilities;
* tightly coupled code that prevents meaningful testing;
* unclear ownership of external API behavior.

Avoid refactoring merely to apply a preferred pattern.

Do not create abstractions until their responsibility can be clearly named.

Three simple functions are often better than an elaborate generic framework.

---

# Code Review Standard

Before finishing, review the diff as if reviewing another engineer's pull request.

Check for:

* accidental unrelated changes;
* missing error handling;
* API failure behavior;
* missing timeouts;
* incorrect async behavior;
* duplicated logic;
* poorly named abstractions;
* leaked implementation details;
* untested behavior;
* secrets or sensitive information;
* unnecessary dependencies;
* stale comments or documentation.

Prefer code that another developer can understand without needing the original task conversation.

---

# Agent Behavior

When working on a task:

* investigate before editing;
* follow existing patterns;
* keep changes scoped;
* make reasonable decisions without excessive back-and-forth;
* verify assumptions against the repository;
* run relevant tests and quality checks;
* report limitations accurately.

Do not:

* invent files, APIs, endpoints, or repository behavior you have not inspected;
* claim tests were run when they were not;
* ignore failing checks;
* expose secrets;
* make destructive changes without explicit justification;
* use broad exception handling to make errors disappear;
* weaken tests merely to make them pass;
* remove validation because input is "expected" to be valid;
* bypass architecture for expediency when a clean implementation is straightforward.

When uncertain, prefer inspecting more of the existing code over guessing.

---

# Completion Report

When completing a coding task, provide a concise summary containing:

1. what changed;
2. important implementation decisions;
3. validation performed;
4. any remaining risks or limitations.

Do not provide a lengthy narration of every file inspected or command executed.

A good completion report looks like:

```text
Implemented:
- Added typed client support for the upstream orders endpoint.
- Moved order filtering into OrderService.
- Added handling for API timeouts and malformed responses.
- Added regression tests for pagination and timeout behavior.

Validation:
- pytest tests/services/test_orders.py: passed
- pytest tests/clients/test_orders.py: passed
- ruff check .: passed

Notes:
- Full integration tests require API credentials and were not run.
```

Be precise and concise.
