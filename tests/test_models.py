"""Job.id must separate genuinely distinct reqs without churning on cosmetic URL
differences — the dedup in cmd_scan drops every collision silently."""

from jobradar.models import Job


def _job(**kw) -> Job:
    base = dict(company="Amazon", title="Verification Engineer", location="Tel Aviv")
    base.update(kw)
    return Job(**base)


def test_distinct_reqs_with_same_title_and_city_get_distinct_ids():
    a = _job(url="https://www.amazon.jobs/en/jobs/10467279/verification-engineer")
    b = _job(url="https://www.amazon.jobs/en/jobs/3144789/verification-engineer")
    assert a.id != b.id


def test_query_string_does_not_churn_the_id():
    a = _job(url="https://www.comeet.com/jobs/gilat/39.005/x/6E.86C")
    b = _job(url="https://www.comeet.com/jobs/gilat/39.005/x/6E.86C?coref=1.11.p7A")
    assert a.id == b.id


def test_host_does_not_churn_the_id():
    # e.g. a Lever board read from the EU endpoint instead of the US one
    a = _job(url="https://jobs.lever.co/mobileye/abc-123")
    b = _job(url="https://jobs.eu.lever.co/mobileye/abc-123")
    assert a.id == b.id


def test_urlless_job_still_gets_a_stable_id():
    assert _job(url="").id == _job(url="").id
