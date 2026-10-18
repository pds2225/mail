from scripts.check_group_rules import find_conflicts


def test_checker_finds_keyword_region_type_and_include_exclude_conflicts():
    groups = [
        {
            "id": "north",
            "or_keywords": ["스마트 공장"],
            "exclude_keywords": [],
            "support_types": ["지원금/바우처"],
            "required_conditions": {"regions": ["서울"]},
        },
        {
            "id": "south",
            "or_keywords": ["스마트 공장"],
            "exclude_keywords": ["스마트 공장"],
            "support_types": ["투자"],
            "required_conditions": {"regions": ["부산"]},
        },
    ]
    findings = find_conflicts(groups)
    assert {finding["kind"] for finding in findings} == {
        "include_exclude", "region_conflict", "support_type_conflict"
    }


def test_checker_ignores_unrelated_groups():
    assert find_conflicts([{"id": "a", "or_keywords": ["바우처"]},
                           {"id": "b", "or_keywords": ["전시회"]}]) == []
