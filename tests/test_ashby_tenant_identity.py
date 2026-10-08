import pytest
from scripts.employer_resolution_queue import _hint_identity_status
from scripts.careers_resolver import has_provider_tenant_identity

def test_ashby_hint_identity_status():
    assert _hint_identity_status("https://jobs.ashbyhq.com") == "tenant"
    assert _hint_identity_status("https://ashbyhq.com") == "tenant"
    assert _hint_identity_status("https://jobs.lever.co") == "tenant"
    assert _hint_identity_status("https://boards.greenhouse.io") == "tenant"
    assert _hint_identity_status("https://jobs.ashbyhq.com/company") == "tenant"

def test_has_provider_tenant_identity_ashby():
    assert has_provider_tenant_identity("https://jobs.ashbyhq.com/company", "ashby") is True
    assert has_provider_tenant_identity("https://jobs.ashbyhq.com/jobs", "ashby") is False
    assert has_provider_tenant_identity("https://jobs.ashbyhq.com/careers", "ashby") is False
    assert has_provider_tenant_identity("https://ashbyhq.com/jobs", "ashby") is False
