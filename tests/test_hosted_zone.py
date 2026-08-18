import cfn_extras.hosted_zone as hosted_zone


class FakeRoute53:
    """Records the DELETE changes issued, and serves record sets across an
    arbitrary number of paginator pages."""

    def __init__(self, pages):
        self._pages = pages
        self.deleted = []

    def get_paginator(self, name):
        assert name == 'list_resource_record_sets'
        pages = self._pages

        class _Paginator:
            def paginate(self, HostedZoneId):
                for page in pages:
                    yield {'ResourceRecordSets': page}

        return _Paginator()

    def change_resource_record_sets(self, HostedZoneId, ChangeBatch):
        change = ChangeBatch['Changes'][0]
        assert change['Action'] == 'DELETE'
        self.deleted.append(change['ResourceRecordSet'])


def test_delete_removes_only_non_ns_soa_across_pages(monkeypatch):
    pages = [
        [{'Type': 'NS', 'Name': 'z.'}, {'Type': 'A', 'Name': 'a.z.'}],
        [{'Type': 'SOA', 'Name': 'z.'}, {'Type': 'TXT', 'Name': 't.z.'}],
    ]
    fake = FakeRoute53(pages)
    monkeypatch.setattr(hosted_zone, 'route53', fake)

    hosted_zone.delete({'ResourceProperties': {'HostedZoneId': 'Z123'}}, None)

    # NS/SOA left intact; A/TXT removed - proving both the filter and that
    # every page was walked.
    assert [r['Type'] for r in fake.deleted] == ['A', 'TXT']


def test_delete_no_deletable_records_is_noop(monkeypatch):
    fake = FakeRoute53([[{'Type': 'NS', 'Name': 'z.'}, {'Type': 'SOA', 'Name': 'z.'}]])
    monkeypatch.setattr(hosted_zone, 'route53', fake)

    hosted_zone.delete({'ResourceProperties': {'HostedZoneId': 'Z123'}}, None)

    assert fake.deleted == []


def test_create_update_is_noop(monkeypatch):
    fake = FakeRoute53([])
    monkeypatch.setattr(hosted_zone, 'route53', fake)

    physical = hosted_zone.create_or_update(
        {'LogicalResourceId': 'HostedZoneManager', 'ResourceProperties': {'HostedZoneId': 'Z123'}},
        None,
    )
    assert physical == 'HostedZoneManager'
    assert fake.deleted == []
