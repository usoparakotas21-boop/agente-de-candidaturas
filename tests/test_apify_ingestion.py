from app.apify_ingestion import normalize_apify_record


def test_apify_linkedin_shape_is_mapped_to_job_feed_shape():
    result = normalize_apify_record({
        "id": "123",
        "link": "https://www.linkedin.com/jobs/view/123",
        "title": "Analista de RH",
        "companyName": "Empresa",
        "location": "Salvador, BA",
        "salaryInfo": ["R$ 4.000", "R$ 5.000"],
        "descriptionText": "Recrutamento e seleção",
        "workRemoteAllowed": True,
        "employmentType": "Full-time",
    })
    assert result["external_id"] == "123"
    assert result["company"] == "Empresa"
    assert result["apply_url"].startswith("https://")
    assert result["work_mode"] == "remote"

