import pytest

from app.ats_registry import is_ats_domain, is_redirect_domain


@pytest.mark.parametrize(
    ("url", "expected_name"),
    [
        ("https://gupy.io/vagas/123", "Gupy"),
        ("https://www.gupy.io/vagas/123", "Gupy"),
        ("https://jobs.gupy.io/vagas/123", "Gupy"),
        ("https://vagas.solides.com.br/vagas/123", "Solides Vagas"),
        ("https://www.jobbol.com.br/vagas/123", "Jobbol"),
        ("HTTPS://CAREERS.LINKEDIN.COM/jobs", "LinkedIn"),
        ("https://gupy.io.:443/jobs", "Gupy"),
    ],
)
def test_is_ats_domain_accepts_exact_and_true_subdomains(url, expected_name):
    assert is_ats_domain(url) == (True, expected_name)


@pytest.mark.parametrize(
    "url",
    [
        "https://gupy.io.evil.example/jobs",
        "https://evilgupy.io/jobs",
        "https://gupy-io.example/jobs",
        "https://gupy.io@evil.example/jobs",
        "https://user@gupy.io/jobs",
        "https://gupy.io\\@evil.example/jobs",
        "//gupy.io/jobs",
        "javascript://gupy.io/jobs",
        "https://gupy.io:invalid/jobs",
        "https://gupy.io../jobs",
        " https://gupy.io/jobs",
        "https://gupy。io/jobs",
    ],
)
def test_is_ats_domain_rejects_forged_or_ambiguous_urls(url):
    assert is_ats_domain(url) == (False, None)


@pytest.mark.parametrize(
    "url",
    [
        "https://bit.ly/abc123",
        "https://www.bit.ly/abc123",
        "https://go.tinyurl.com/abc123",
        "https://lnkd.in/abc123",
    ],
)
def test_is_redirect_domain_accepts_exact_and_true_subdomains(url):
    assert is_redirect_domain(url) is True


@pytest.mark.parametrize(
    "url",
    [
        "https://bit.ly.evil.example/abc123",
        "https://notbit.ly/abc123",
        "https://bit.ly@evil.example/abc123",
        "https://user@bit.ly/abc123",
        "https://bit.ly\\@evil.example/abc123",
        "//bit.ly/abc123",
        "https://bit.ly:invalid/abc123",
        "https://bit.ly。evil.example/abc123",
    ],
)
def test_is_redirect_domain_rejects_forged_or_ambiguous_urls(url):
    assert is_redirect_domain(url) is False
