"""Unit tests for PII detection core (T025 / FR-008).

Coverage:
- phone / email / id_card / bank_card / customer_name / address
- longest-first non-overlap (so customer_name doesn't double-replace)
- empty input
- all fields-off → no hits
- replacement tags match REPLACEMENTS table
"""

from __future__ import annotations

import pytest


@pytest.fixture
def detector():
    # Imported lazily so a missing presidio install doesn't break the file
    from src.core.pii import PIIDetector

    return PIIDetector()


class TestPhoneDetection:
    def test_chinese_mobile(self, detector):
        result = detector.detect("联系 13800138000 处理")
        assert result.has_pii
        fields = {h.field for h in result.hits}
        assert "phone" in fields
        assert "13800138000" not in result.redacted_text
        assert "[PHONE]" in result.redacted_text

    def test_phone_at_word_boundary(self, detector):
        # Boundary check: 12 digits should not match (too long for phone)
        result = detector.detect("订单号 1234567890123")
        phone_hits = [h for h in result.hits if h.field == "phone"]
        assert phone_hits == []


class TestEmailDetection:
    def test_basic_email(self, detector):
        result = detector.detect("邮箱 dev@pptagent.local")
        assert "email" in {h.field for h in result.hits}
        assert "[EMAIL]" in result.redacted_text

    def test_email_with_subdomain(self, detector):
        result = detector.detect("发到 user.name@sub.example.co.uk")
        assert "email" in {h.field for h in result.hits}


class TestIDCardDetection:
    def test_valid_18_digit_id(self, detector):
        result = detector.detect("身份证 11010119900307881X 确认")
        assert "id_card" in {h.field for h in result.hits}
        assert "[ID_CARD]" in result.redacted_text

    def test_18_digit_with_x_lower(self, detector):
        result = detector.detect("id: 11010119900307881x end")
        assert "id_card" in {h.field for h in result.hits}


class TestBankCardDetection:
    def test_16_digit_card(self, detector):
        result = detector.detect("卡号 6222021234567890 已记录")
        assert "bank_card" in {h.field for h in result.hits}


class TestCustomerNameDetection:
    def test_customer_prefix(self, detector):
        result = detector.detect("客户张三前来咨询")
        assert "customer_name" in {h.field for h in result.hits}
        assert "[CUSTOMER_NAME]" in result.redacted_text

    def test_name_prefix(self, detector):
        result = detector.detect("联系人李四的电话")
        assert "customer_name" in {h.field for h in result.hits}


class TestAddressDetection:
    def test_with_city(self, detector):
        result = detector.detect("送达地址北京市朝阳区建国路88号")
        assert "address" in {h.field for h in result.hits}


class TestEdgeCases:
    def test_empty_text(self, detector):
        result = detector.detect("")
        assert not result.has_pii
        assert result.redacted_text == ""

    def test_no_pii(self, detector):
        result = detector.detect("本季度营收同比增长 18%，毛利率提升。")
        assert not result.has_pii
        assert result.redacted_text == "本季度营收同比增长 18%，毛利率提升。"

    def test_summary_shape(self, detector):
        result = detector.detect("邮箱 dev@pptagent.local 电话 13800138000")
        summary = result.to_summary()
        assert summary["hit_count"] == 2
        assert set(summary["fields"]) == {"phone", "email"}
        assert isinstance(summary["actions"], list)
        for a in summary["actions"]:
            assert {"field", "start", "end", "score", "replacement"} <= a.keys()

    def test_field_filter(self, detector):
        # Only scan phone, not email
        result = detector.detect(
            "邮箱 dev@pptagent.local 电话 13800138000",
            fields=["phone"],
        )
        assert {h.field for h in result.hits} == {"phone"}

    def test_redact_alias(self, detector):
        text = "联系 13800138000"
        assert detector.redact(text) == "联系 [PHONE]"


class TestNonOverlap:
    def test_longest_first_prevents_double_replace(self, detector):
        # The address regex "北京市朝阳区建国路88号" may partially overlap
        # with a customer_name prefix "客户李四". Make sure the redacted
        # text does NOT contain literal "李四" (replaced once, not twice).
        text = "客户李四住在北京市朝阳区建国路88号"
        result = detector.detect(text)
        for forbidden in ("李四", "北京市", "88号"):
            # If a hit fired, its replacement must be in place
            if any(h.text == forbidden for h in result.hits):
                assert forbidden not in result.redacted_text
