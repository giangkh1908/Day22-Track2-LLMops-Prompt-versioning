"""
Bước 4 — Guardrails AI Validators
====================================
NHIỆM VỤ:
  1. Xây dựng PIIDetector: phát hiện & redact email, số điện thoại, SSN, số thẻ tín dụng
  2. Xây dựng JSONFormatter: tự động sửa JSON lỗi
  3. Bọc mỗi validator trong Guard và test với các mẫu đầu vào
  4. Chạy demo với 6 trường hợp PII và 5 trường hợp JSON

DELIVERABLE: Tất cả test cases pass (PII bị redact, JSON được sửa thành công)

CÁC KHÁI NIỆM CHÍNH:
  - @register_validator     — khai báo custom validator class
  - Validator.validate()    — implement logic kiểm tra + sửa
  - OnFailAction.FIX        — thay thế output thay vì raise error
  - Guard().use(validator)  — gắn validator instance vào guard
  - guard.validate(text)    → ValidationOutcome
      .validation_passed    — bool
      .validated_output     — output đã được xử lý

⚠️  QUAN TRỌNG: on_fail phải truyền vào CONSTRUCTOR của VALIDATOR, KHÔNG phải Guard.use()
    SAI  : Guard().use(PIIDetector, on_fail=OnFailAction.FIX)   ← TypeError
    ĐÚNG : Guard().use(PIIDetector(on_fail=OnFailAction.FIX))   ← correct
"""

import re
import json

from guardrails import Guard
from guardrails.validators import Validator, register_validator, PassResult, FailResult

try:
    from guardrails.hub import OnFailAction
except ImportError:
    from guardrails.validator_base import OnFailAction


# ── 1. PII Detector Validator ──────────────────────────────────────────────
@register_validator(name="custom/pii-detector", data_type="string")
class PIIDetector(Validator):
    """
    Phát hiện và redact Personally Identifiable Information (PII).

    Các pattern được phát hiện:
      EMAIL       : xxx@xxx.xxx
      PHONE       : (123) 456-7890 hoặc 123-456-7890
      SSN         : 123-45-6789
      CREDIT_CARD : 1234 5678 9012 3456 (hoặc dấu gạch nối)
    """

    # Regex patterns cho từng loại PII — đã được định nghĩa sẵn, bạn chỉ cần dùng
    PII_PATTERNS = {
        "EMAIL":       r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
        "PHONE":       r"(?:\+?1[-.\s]?)?(?:\(\d{3}\)|\d{3})[-.\s]\d{3}[-.\s]\d{4}\b",
        "SSN":         r"\b\d{3}-\d{2}-\d{4}\b",
        "CREDIT_CARD": r"\b(?:\d{4}[-\s]?){3}\d{4}\b",
    }

    def validate(self, value: str, metadata: dict):
        """
        Tìm PII trong value; nếu phát hiện, redact và trả về FailResult với fix_value.

        Bước:
          1. Copy value → redacted_text
          2. Với mỗi loại PII và pattern tương ứng:
             - Tìm tất cả matches bằng re.findall(pattern, value)
             - Thay thế từng match bằng "[PII_TYPE_REDACTED]" trong redacted_text
             - Ghi lại (pii_type, match) vào found_pii
          3. Nếu found_pii không rỗng → FailResult(fix_value=redacted_text)
          4. Nếu không tìm thấy PII → PassResult()
        """
        redacted_text = value
        found_pii     = []

        # TODO hoàn thành: Lặp qua self.PII_PATTERNS.items().
        for pii_type, pattern in self.PII_PATTERNS.items():
            # TODO hoàn thành: Tìm tất cả matches.
            matches = re.findall(pattern, value)

            for match in matches:
                # TODO hoàn thành: Thay thế match bằng "[PII_TYPE_REDACTED]" trong redacted_text.
                redacted_text = redacted_text.replace(match, f"[{pii_type}_REDACTED]")
                found_pii.append((pii_type, match))

        if found_pii:
            print(f"  Redacted {len(found_pii)} PII item(s): {[p[0] for p in found_pii]}")
            # TODO hoàn thành: Trả về FailResult với fix_value để OnFailAction.FIX thay output.
            return FailResult(
                error_message=f"PII detected: {[p[0] for p in found_pii]}",
                fix_value=redacted_text,
            )

        # TODO hoàn thành: Không có PII → pass validation.
        return PassResult()


# ── 2. JSON Formatter Validator ────────────────────────────────────────────
@register_validator(name="custom/json-formatter", data_type="string")
class JSONFormatter(Validator):
    """
    Validate và tự động sửa JSON lỗi.

    Các lỗi có thể sửa tự động:
      - Strip markdown code fences (``` hoặc ```json)
      - Thay single quotes → double quotes
      - Xóa trailing commas trước } hoặc ]
      - Re-serialize với json.dumps để định dạng chuẩn
    """

    @staticmethod
    def _repair(text: str) -> str:
        """
        Cố gắng sửa chuỗi JSON lỗi.

        Bước:
          1. Strip whitespace đầu/cuối
          2. Xóa markdown fences bằng re.sub
          3. Thay single quotes → double quotes
          4. Xóa trailing commas trước } hoặc ]
          5. Trả về chuỗi đã sửa (chưa re-serialize)
        """
        text = text.strip()

        # Xóa markdown fences — đã cho sẵn
        text = re.sub(r'^```(?:json)?\s*', '', text)
        text = re.sub(r'\s*```$',          '', text)
        text = text.strip()

        # TODO hoàn thành: Thay single quotes → double quotes.
        text = text.replace("'", '"')

        # TODO hoàn thành: Xóa trailing commas (dùng re.sub với r',\s*([}\]])' → r'\1').
        text = re.sub(r',\s*([}\]])', r'\1', text)

        return text

    def validate(self, value: str, metadata: dict):
        """
        Thử parse value thành JSON.
        Nếu thất bại, gọi _repair() rồi thử lại.

        Trả về PassResult nếu JSON đã hợp lệ.
        Trả về FailResult với fix_value nếu JSON sửa được hoặc cần fallback.
        """
        # TODO hoàn thành: Thử parse JSON trực tiếp.
        try:
            parsed = json.loads(value)
            # TODO hoàn thành: JSON đã hợp lệ thì pass validation.
            return PassResult()
        except json.JSONDecodeError:
            pass

        # TODO hoàn thành: Thử sửa JSON rồi parse lại.
        try:
            repaired_text = self._repair(value)
            parsed        = json.loads(repaired_text)
            print("  JSON repaired successfully")
            # TODO hoàn thành: Trả về FailResult với fix_value để OnFailAction.FIX thay output.
            return FailResult(
                error_message="JSON was repaired automatically",
                fix_value=json.dumps(parsed, ensure_ascii=False, indent=2),
            )
        except json.JSONDecodeError as e:
            fallback = json.dumps(
                {
                    "error": "JSON is still invalid after repair",
                    "detail": str(e),
                    "raw": value[:200],
                },
                ensure_ascii=False,
                indent=2,
            )
            return FailResult(
                error_message=f"JSON is still invalid after repair: {e}",
                fix_value=fallback,
            )


# ── 3. Demo: PII Guard ─────────────────────────────────────────────────────
def demo_pii_guard():
    print("\n" + "=" * 55)
    print("  Demo: PII Detection & Redaction")
    print("=" * 55)

    # TODO hoàn thành: Tạo Guard với PIIDetector, truyền on_fail=OnFailAction.FIX vào CONSTRUCTOR.
    # Gợi ý: guard = Guard().use(PIIDetector(on_fail=OnFailAction.FIX))
    guard = Guard().use(PIIDetector(on_fail=OnFailAction.FIX))

    test_cases = [
        ("Email",        "Contact John at john.doe@example.com for details."),
        ("Phone",        "Call our support line at (555) 867-5309."),
        ("SSN",          "Patient SSN is 123-45-6789 on file."),
        ("Credit Card",  "Payment made with card 4532 1234 5678 9010."),
        ("Multi-PII",    "Email: alice@example.com, Phone: 555-123-4567"),
        ("Clean",        "No sensitive information in this text."),
    ]

    for label, text in test_cases:
        # TODO hoàn thành: Gọi guard.validate(text) để lấy ValidationOutcome.
        result = guard.validate(text)

        print(f"\n[{label}]")
        print(f"  Input:  {text}")
        print(f"  Output: {result.validated_output}")


# ── 4. Demo: JSON Guard ────────────────────────────────────────────────────
def demo_json_guard():
    print("\n" + "=" * 55)
    print("  Demo: JSON Formatting & Repair")
    print("=" * 55)

    # TODO hoàn thành: Tạo Guard với JSONFormatter, truyền on_fail=OnFailAction.FIX vào CONSTRUCTOR.
    # Gợi ý: guard = Guard().use(JSONFormatter(on_fail=OnFailAction.FIX))
    guard = Guard().use(JSONFormatter(on_fail=OnFailAction.FIX))

    test_cases = [
        ("Valid JSON",       '{"name": "Alice", "age": 30}'),
        ("Markdown fences",  '```json\n{"name": "Bob"}\n```'),
        ("Single quotes",    "{'name': 'Charlie', 'score': 95}"),
        ("Trailing comma",   '{"key": "value",}'),
        ("Truly invalid",    "This is not JSON at all: ??? {]"),
    ]

    for label, text in test_cases:
        # TODO hoàn thành: Gọi guard.validate(text) để lấy ValidationOutcome.
        result = guard.validate(text)

        status = "PASS" if result.validation_passed else "FAIL"
        print(f"\n[{label}] {status}")
        print(f"  Input:  {text[:60]}")
        print(f"  Output: {str(result.validated_output)[:60]}")


# ── 5. Main ────────────────────────────────────────────────────────────────
def main():
    print("=" * 55)
    print("  Step 4: Guardrails AI Validators")
    print("=" * 55)

    demo_pii_guard()
    demo_json_guard()

    print("\nStep 4 completed!")


if __name__ == "__main__":
    main()
