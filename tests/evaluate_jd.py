
import json
from pathlib import Path

from app.llm_service import analyze_jd_with_llm


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEST_CASES_PATH = PROJECT_ROOT / "data" / "jd_test_cases.json"


def normalize(value):
    if isinstance(value, list):
        return sorted(value)
    return value


def main():
    with TEST_CASES_PATH.open("r", encoding="utf-8") as file:
        test_cases = json.load(file)

    passed = 0
    failed = 0
    error_count = 0

    for case in test_cases:
        print(f"\n--- {case['id']} ---")

        try:
            result = analyze_jd_with_llm(case["input"])
            actual = result.model_dump(mode="json")
        except Exception as exc:
            error_count += 1
            print(f"结果：ERROR | {type(exc).__name__}: {exc}")
            continue

        errors = []

        for field, expected in case["expected"].items():
            actual_value = actual.get(field)

            if normalize(actual_value) != normalize(expected):
                errors.append(
                    (field, expected, actual_value)
                )

        if errors:
            failed += 1
            print("结果：FAIL")

            for field, expected, actual_value in errors:
                print(f"  字段：{field}")
                print(f"  期望：{expected}")
                print(f"  实际：{actual_value}")
        else:
            passed += 1
            print("结果：PASS")

    print("\n========== 评测汇总 ==========")
    print(f"测试总数：{len(test_cases)}")
    print(f"通过数量：{passed}")
    print(f"失败数量：{failed}")
    print(f"错误数量：{error_count}")

    evaluated = passed + failed

    if evaluated:
        accuracy = passed / evaluated * 100
        print(f"可评估案例通过率：{accuracy:.1f}%")
    else:
        print("可评估案例通过率：暂无（没有成功获得模型结果）")


if __name__ == "__main__":
    main()
