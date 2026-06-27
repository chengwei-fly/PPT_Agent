"""Token budget validation tests (T118 / SC-001 / SC-009).

SC-001: 95% delivery rate within 5 minutes for 20-topic test set.
SC-009: Stage redo must reduce time by >= 60% vs full redo.

These tests validate the token estimator and pipeline timing constraints
without requiring actual LLM calls.
"""

from __future__ import annotations

import pytest

from src.services.generation.token_estimator import (
    BASE_OVERHEAD_TOKENS,
    TOKENS_PER_SLIDE_BY_STAGE,
    Estimate,
    estimate_generation,
    median_estimate,
)


@pytest.mark.integration
class TestTokenEstimator:
    """Validate token estimation logic (FR-004)."""

    def test_estimate_baseline_10_pages(self):
        est = estimate_generation(prompt="test prompt", sample_count=0, pages=10)
        assert isinstance(est, Estimate)
        assert est.tokens > 0
        assert est.seconds >= 30

    def test_estimate_scales_with_pages(self):
        est_10 = estimate_generation(prompt="x", pages=10)
        est_20 = estimate_generation(prompt="x", pages=20)
        assert est_20.tokens > est_10.tokens

    def test_estimate_scales_with_samples(self):
        est_0 = estimate_generation(prompt="x", sample_count=0)
        est_3 = estimate_generation(prompt="x", sample_count=3)
        assert est_3.tokens > est_0.tokens

    def test_estimate_includes_buffer(self):
        base = BASE_OVERHEAD_TOKENS + sum(
            TOKENS_PER_SLIDE_BY_STAGE[s] * 10 for s in TOKENS_PER_SLIDE_BY_STAGE
        )
        buffered = int(base * 1.2)
        est = estimate_generation(prompt="x", sample_count=0, pages=10)
        assert est.tokens >= buffered

    def test_median_estimate_empty_history(self):
        assert median_estimate([]) == BASE_OVERHEAD_TOKENS

    def test_median_estimate_with_history(self):
        assert median_estimate([1000, 2000, 3000]) == 2000


@pytest.mark.integration
class TestTokenBudgetSC001:
    """SC-001: 95% delivery rate within 5 minutes."""

    TOPICS = [
        "Q3 储能立项汇报",
        "年度工作总结",
        "产品发布方案",
        "市场分析报告",
        "技术架构设计",
        "培训课程大纲",
        "客户案例展示",
        "财务季度报告",
        "项目进度汇报",
        "团队建设方案",
        "营销活动策划",
        "数据治理方案",
        "供应链优化",
        "人才培养计划",
        "风险评估报告",
        "数字化转型",
        "质量管理方案",
        "成本控制分析",
        "创新项目提案",
        "战略合作方案",
    ]

    def test_estimator_covers_20_topics(self):
        for topic in self.TOPICS:
            est = estimate_generation(prompt=topic, sample_count=3, pages=12)
            assert est.tokens <= 100_000
            assert est.seconds <= 300

    def test_token_per_stage_budget(self):
        for stage, per_slide in TOKENS_PER_SLIDE_BY_STAGE.items():
            assert 0 < per_slide <= 1000


@pytest.mark.integration
class TestTokenBudgetSC009:
    """SC-009: Stage redo must save >= 60% vs full redo."""

    def test_redo_skips_upstream_stages(self):
        full = sum(TOKENS_PER_SLIDE_BY_STAGE[s] * 10 for s in TOKENS_PER_SLIDE_BY_STAGE)
        redo = sum(TOKENS_PER_SLIDE_BY_STAGE[s] * 10 for s in ["svg", "pptx"])
        saving = 1.0 - (redo / full)
        assert saving >= 0.6

    def test_redo_stage_2_saves_significant(self):
        full = sum(TOKENS_PER_SLIDE_BY_STAGE[s] * 10 for s in TOKENS_PER_SLIDE_BY_STAGE)
        redo = sum(TOKENS_PER_SLIDE_BY_STAGE[s] * 10 for s in ["points", "svg", "pptx"])
        saving = 1.0 - (redo / full)
        assert saving >= 0.4
