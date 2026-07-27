from mail_core.operations import source_field_quality as sfq


def _good_item():
    return {
        "title": "2026년 AI 예비창업자 지원사업",
        "description": "서울 거주 AI 예비창업자의 사업화를 지원합니다. " * 6,
        "posted_date": "2026-07-27",
        "deadline": "2026-08-31",
        "target_field": "예비창업자",
        "detail_extraction": {
            "status": "SUCCESS",
            "fields": {
                "description": {"status": "SUCCESS"},
                "application_period": {"status": "SUCCESS"},
                "target": {"status": "SUCCESS"},
            },
        },
    }


def test_evaluate_source_items_measures_body_not_short_category():
    good = _good_item()
    short = {
        **_good_item(),
        "description": "사업화",
        "detail_extraction": {
            "status": "SUCCESS",
            "fields": {
                "description": {"status": "SUCCESS"},
                "application_period": {"status": "SUCCESS"},
                "target": {"status": "NOT_SPECIFIED"},
            },
        },
        "target_field": "",
    }
    result = sfq.evaluate_source_items("kstartup", [good, short])
    assert result["fields"]["body"]["read_rate"] == 0.5
    assert result["fields"]["target"]["read_rate"] == 1.0
    assert result["fields"]["target"]["value_rate"] == 0.5


def test_repeated_fingerprint_escalates_from_p1_to_p0():
    metrics = {
        "kita": sfq.evaluate_source_items(
            "kita",
            [{**_good_item(), "description": "수출"}],
        )
    }
    first = sfq.build_quality_report(metrics, history={"runs": []})
    assert first["status"] == "P1"
    assert first["issues"][0]["fingerprint"] == "kita:body"

    history = {
        "runs": [{
            "sources": first["sources"],
            "fingerprints": first["fingerprints"],
        }]
    }
    second = sfq.build_quality_report(metrics, history=history)
    issue = next(i for i in second["issues"] if i["fingerprint"] == "kita:body")
    assert issue["severity"] == "P0"
    assert issue["repeat_count"] == 2


def test_bizinfo_and_kstartup_failures_are_p0_immediately():
    for site_id in ("bizinfo", "kstartup"):
        metrics = {
            site_id: sfq.evaluate_source_items(
                site_id,
                [{**_good_item(), "description": "사업화"}],
            )
        }
        report = sfq.build_quality_report(metrics, history={"runs": []})
        issue = next(i for i in report["issues"] if i["field"] == "body")
        assert issue["severity"] == "P0"


def test_learned_baseline_flags_large_regression():
    good_metrics = {"bizinfo": sfq.evaluate_source_items("bizinfo", [_good_item()] * 3)}
    history = {
        "runs": [
            {"sources": good_metrics, "fingerprints": []},
            {"sources": good_metrics, "fingerprints": []},
            {"sources": good_metrics, "fingerprints": []},
        ]
    }
    regressed_item = {**_good_item(), "description": "기술개발"}
    current = {
        "bizinfo": sfq.evaluate_source_items(
            "bizinfo",
            [regressed_item, regressed_item, _good_item()],
        )
    }
    report = sfq.build_quality_report(current, history=history)
    body = next(i for i in report["issues"] if i["fingerprint"] == "bizinfo:body")
    assert "FIELD_READ_RATE_REGRESSION" in body["reason"]
    assert body["baseline_median"] == 1.0


def test_history_contains_metrics_and_fingerprints_only(tmp_path):
    report = sfq.build_quality_report(
        {"nipa": sfq.evaluate_source_items("nipa", [_good_item()])},
        history={"runs": []},
    )
    path = tmp_path / "history.json"
    sfq.append_history({"runs": []}, report, path=path)
    text = path.read_text(encoding="utf-8")
    assert "서울 거주" not in text
    assert '"sources"' in text
    assert '"fingerprints"' in text
