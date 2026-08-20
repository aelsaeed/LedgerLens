# ADR 001: Remove the unvalidated vendor classifier from invoice processing

- **Status:** Accepted
- **Date:** 2026-08-20
- **Decision owners:** LedgerLens maintainers

## Context

The first prototype included a small PyTorch `VendorClassifier`. Its training fixture contained
four rows across three vendor names:

- `Acme Corp` → class `0` (twice)
- `Globex` → class `1`
- `Umbrella` → class `2`

The model used a one-hot feature for the first token of a vendor name and emitted labels such as
`vendor_0`. There was no held-out evaluation set, documented business meaning for those labels,
probability calibration, or production dataset.

For an unseen vendor, the feature vector was all zeros. The network still selected the largest
logit and returned a label and softmax score. That result looked like model confidence even though
the input contained no recognized feature. Keeping it in the request path would therefore make
the response less trustworthy.

## Decision

Remove the classifier, its training stub, and the PyTorch runtime dependency from the invoice
processing path. Build the current product around capabilities that can be demonstrated and
audited:

- deterministic field extraction with source evidence;
- exact-decimal invoice reconciliation;
- explicit warnings and missing-field reporting; and
- transparent human-review routing.

The quality score is documented as a workflow heuristic rather than a learned probability.
LedgerLens makes no claim that it classifies vendors, detects fraud, or predicts payment approval.

## Consequences

### Positive

- Unknown vendors no longer receive arbitrary labels.
- The response contract contains only fields whose provenance and behavior can be explained.
- Installation and containers are smaller because PyTorch is no longer required.
- Tests can assert deterministic behavior without depending on random initialization or a model
  artifact.
- The portfolio demonstrates model-risk judgment, not merely model integration.

### Negative

- The current application does not demonstrate a trained ML inference path.
- New layouts and classification use cases require rules or future, properly evaluated models.
- Removing the stub postpones work on artifact versioning, feature drift, and model serving.

## Conditions for revisiting

An ML component can return when the repository has all of the following:

1. A clearly defined prediction target with labels that have business meaning.
2. A legally usable, versioned, representative dataset and documented data provenance.
3. Train/validation/test splits that prevent vendor or document-template leakage.
4. A simple baseline and reported per-class metrics on held-out data—not training accuracy.
5. Calibration or an abstention policy so unknown and low-confidence inputs route to review.
6. A versioned preprocessing and model artifact contract with reproducible training.
7. Tests for out-of-distribution input, monitoring expectations, and a rollback path.

Until those conditions exist, deterministic validation is the more credible product feature.

## Alternatives considered

### Keep the model as an optional demo

Rejected. An optional flag would reduce runtime impact but would not fix the lack of meaningful
labels, evaluation, or safe unknown-vendor behavior.

### Add an `unknown` threshold to the existing model

Rejected. A threshold on uncalibrated softmax output from four training rows would create the
appearance of rigor without supporting evidence.

### Replace it with an external LLM

Deferred. That would introduce privacy, cost, availability, prompt-versioning, and evaluation
questions while leaving the underlying dataset problem unresolved.
