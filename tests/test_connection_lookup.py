import pytest

from cfn_extras.connection_lookup import (
    ConnectionResolver,
    ConnectionLookupEvent,
    resolve_connection_arn,
    parse_event,
    CFN_STACK_SYNC,
)


ARN = "arn:aws:codeconnections:us-east-1:123456789012:connection/abcd-1234-ef56"


class FakeConnectionResolver(ConnectionResolver):
    """In-memory ConnectionResolver so the resolution logic can be tested
    without touching AWS. Records calls so tests can assert on the exact
    triangulation path taken."""

    def __init__(self, sync_configuration=None, repository_links=None):
        self._sync_configuration = sync_configuration if sync_configuration is not None else {}
        self._repository_links = repository_links if repository_links is not None else {}
        self.sync_calls = []
        self.link_calls = []

    def get_sync_configuration(self, sync_type: str, resource_name: str) -> dict:
        self.sync_calls.append((sync_type, resource_name))
        return self._sync_configuration

    def get_repository_link(self, repository_link_id: str) -> dict:
        self.link_calls.append(repository_link_id)
        return self._repository_links.get(repository_link_id, {})


def test_resolve_happy_path_triangulates_via_stack_name():
    resolver = FakeConnectionResolver(
        sync_configuration={'SyncConfiguration': {'RepositoryLinkId': 'link-1'}},
        repository_links={'link-1': {'RepositoryLinkInfo': {'ConnectionArn': ARN}}},
    )
    event = ConnectionLookupEvent(stack_name='domains')

    assert resolve_connection_arn(resolver, event) == ARN
    # Verifies the exact path: sync config looked up by stack name, then the
    # repository link resolved from the returned id.
    assert resolver.sync_calls == [(CFN_STACK_SYNC, 'domains')]
    assert resolver.link_calls == ['link-1']


def test_resolve_no_sync_configuration_raises():
    resolver = FakeConnectionResolver(sync_configuration={})
    event = ConnectionLookupEvent(stack_name='domains')

    with pytest.raises(Exception, match="No CFN_STACK_SYNC sync configuration"):
        resolve_connection_arn(resolver, event)
    # Must not attempt a repository link lookup when there is no sync config.
    assert resolver.link_calls == []


def test_resolve_missing_repository_link_id_raises():
    resolver = FakeConnectionResolver(sync_configuration={'SyncConfiguration': {}})
    event = ConnectionLookupEvent(stack_name='domains')

    with pytest.raises(Exception, match="No CFN_STACK_SYNC sync configuration"):
        resolve_connection_arn(resolver, event)


def test_resolve_missing_connection_arn_raises():
    resolver = FakeConnectionResolver(
        sync_configuration={'SyncConfiguration': {'RepositoryLinkId': 'link-1'}},
        repository_links={'link-1': {'RepositoryLinkInfo': {}}},
    )
    event = ConnectionLookupEvent(stack_name='domains')

    with pytest.raises(Exception, match="no ConnectionArn"):
        resolve_connection_arn(resolver, event)


def test_resolve_honors_non_default_sync_type():
    resolver = FakeConnectionResolver(
        sync_configuration={'SyncConfiguration': {'RepositoryLinkId': 'link-1'}},
        repository_links={'link-1': {'RepositoryLinkInfo': {'ConnectionArn': ARN}}},
    )
    event = ConnectionLookupEvent(stack_name='domains', sync_type='OTHER_SYNC')

    assert resolve_connection_arn(resolver, event) == ARN
    assert resolver.sync_calls == [('OTHER_SYNC', 'domains')]


def test_parse_event_defaults_sync_type():
    parsed = parse_event({'ResourceProperties': {'StackName': 'domains'}})
    assert parsed == ConnectionLookupEvent(stack_name='domains', sync_type=CFN_STACK_SYNC)


def test_parse_event_reads_explicit_sync_type():
    parsed = parse_event(
        {'ResourceProperties': {'StackName': 'domains', 'SyncType': CFN_STACK_SYNC}}
    )
    assert parsed.stack_name == 'domains'
    assert parsed.sync_type == CFN_STACK_SYNC


def test_parse_event_requires_stack_name():
    with pytest.raises(KeyError):
        parse_event({'ResourceProperties': {}})
