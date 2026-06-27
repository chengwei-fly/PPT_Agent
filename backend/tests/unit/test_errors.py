"""Unit tests for error handling layer (T019 / RFC 7807)."""

from __future__ import annotations


class TestPPTagentError:
    def test_basic_problem_shape(self):
        from src.core.errors import PPTagentError

        err = PPTagentError(code="PPTAGENT.TEST", message="oops")
        problem = err.to_problem(request_id="req-123")
        assert problem["status"] == 400
        assert problem["code"] == "PPTAGENT.TEST"
        assert problem["instance"] == "req-123"
        assert problem["title"] == "oops"
        assert "details" in problem
        assert problem["type"].endswith("/PPTAGENT.TEST")


class TestRateLimitError:
    def test_retry_after_in_details(self):
        from src.core.errors import RateLimitError

        err = RateLimitError(retry_after=42)
        problem = err.to_problem(request_id="rid")
        assert problem["status"] == 429
        assert problem["code"] == "PPTAGENT.RATE_LIMITED"
        assert problem["details"]["retry_after_seconds"] == 42


class TestNotFoundError:
    def test_resource_in_message(self):
        from src.core.errors import NotFoundError

        err = NotFoundError(resource="Sample", resource_id="abc")
        problem = err.to_problem(request_id="rid")
        assert "Sample 'abc' not found" in problem["title"]
        assert problem["details"]["resource"] == "Sample"
        assert problem["details"]["resource_id"] == "abc"


class TestIdempotencyMismatchError:
    def test_message_mentions_key(self):
        from src.core.errors import IdempotencyMismatchError

        err = IdempotencyMismatchError(key="the-key")
        problem = err.to_problem(request_id="rid")
        assert problem["status"] == 422
        assert problem["code"] == "PPTAGENT.IDEMPOTENCY_MISMATCH"
        assert problem["details"]["idempotency_key"] == "the-key"


class TestPIIHitError:
    def test_hit_fields_in_details(self):
        from src.core.errors import PIIHitError

        err = PIIHitError(hit_fields=["phone", "email"], extra="x")
        problem = err.to_problem(request_id="rid")
        assert "phone" in problem["title"]
        assert set(problem["details"]["hit_fields"]) == {"phone", "email"}
        assert problem["details"]["extra"] == "x"
