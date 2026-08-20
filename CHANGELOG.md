# Changelog

All notable changes to LedgerLens are documented here. The project follows
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- Evidence-linked extraction with OCR confidence and bounding boxes.
- Exact `Decimal` normalization for financial values.
- Deterministic line-item, subtotal, total, and date-order checks.
- Quality scoring and explicit human-review routing.
- Versioned image and text extraction APIs plus an interactive dashboard.
- Batch-capable CLI, health endpoint, container workflow, tests, and CI.

### Changed

- Uploads are size- and type-limited, processed off the async event loop, and
  removed immediately after each request.
- OCR failures now return explicit errors instead of successful empty invoices.

### Removed

- The four-record demonstration classifier and mandatory PyTorch dependency.
  It produced arbitrary labels for unseen vendors and had no defensible
  evaluation data.
