from __future__ import annotations

from app.core import classifier


def test_dataset_is_balanced_and_nontrivial():
    labels = [l for _, l in classifier.DATASET]
    assert len(classifier.DATASET) >= 20
    assert 0.35 <= sum(labels) / len(labels) <= 0.65  # not a degenerate single-class set


def test_default_model_is_deterministic():
    a = classifier.default_model()
    b = classifier.classify_log  # noqa: F841
    assert classifier.default_model() is a  # cached singleton


def test_metrics_meet_baseline_threshold():
    m = classifier.evaluate()
    assert m["test_size"] > 0
    # The classifier must clearly beat chance on its own dataset.
    assert m["accuracy"] >= 0.9
    assert m["f1"] >= 0.9


def test_pass_log_classifies_as_passed():
    log = "# pass 4\n# fail 0\n# cancelled 0\n# skipped 0\n# todo 0\n# duration_ms 52.464833"
    label, passed, _conf, agreement = classifier.classify_outcome(0, log)
    assert passed is True
    assert label == "passed"


def test_fail_log_classifies_as_failed():
    log = "# pass 0\n# fail 1\n# cancelled 0\n# duration_ms 10.0"
    label, passed, _conf, agreement = classifier.classify_outcome(1, log)
    assert passed is False
    assert label == "failed"


def test_exit_code_authoritative_against_log_text():
    # exit code 0 but a log that *looks* failing -> still reported failed because exit code wins
    log = "✕ 2 failing\n\n  2 failing"
    label, passed, _conf, agreement = classifier.classify_outcome(0, log)
    assert passed is True  # exit code is authoritative
    assert label == "passed"


def test_classifier_conflict_is_surfaced():
    # exit 1 but log text contains strong pass signals -> classifier-conflict
    label, passed, _conf, agreement = classifier.classify_outcome(
        1, "# pass 4\n# fail 0\n# duration_ms 52"
    )
    assert passed is False
    assert agreement == "classifier-conflict"


def test_predict_proba_is_bounded():
    model = classifier.default_model()
    assert 0.0 <= model.predict_proba("✕ 3 failing") <= 1.0
    assert 0.0 <= model.predict_proba("✓ 3 passed") <= 1.0


def test_classifier_only_path_for_log_without_exit_code():
    label, passed, _conf, agreement = classifier.classify_outcome(None, "✕ 2 failing")
    assert label == "failed"
    assert agreement == "classifier-only"