import pytest
import cfn_extras.domain as index
from cfn_extras.domain import DomainManager, DomainManagerLive

class DomainManagerFake(DomainManager):
    def __init__(self):
        self.events = []
        self.register_kwargs = None
        self.transfer_kwargs = None

    def list_operations(self, **kwargs):
        return {'Operations': []}

    def get_domain_detail(self, domain_name):
        c = _contact()
        boto_contact = {
            'FirstName': c['firstName'],
            'LastName': c['lastName'],
            'ContactType': c['type'],
            'AddressLine1': c['addressLine1'],
            'City': c['city'],
            'State': c['state'],
            'CountryCode': c['countryCode'],
            'ZipCode': c['zipCode'],
            'PhoneNumber': c['phoneNumber'],
            'Email': c['email']
        }
        return {
            'DomainName': domain_name,
            'AdminContact': boto_contact,
            'RegistrantContact': boto_contact,
            'TechContact': boto_contact,
            'AutoRenew': True,
            'Nameservers': []
        }

    def get_operation_detail(self, operation_id):
        self.events.append("get_operation_detail")
        return {'Status': 'SUCCESSFUL'}

    def list_domains(self, **kwargs):
        return {
            'Domains': [
                {
                    'DomainName': "foo.com"
                }
            ]
        }

    def check_domain_availability(self, *args, **kwargs):
        pass

    def register_domain(self, **kwargs):
        self.events.append("register_domain")
        self.register_kwargs = kwargs
        return {'OperationId': 'op-fake-123'}

    def update_domain_nameservers(self, *args, **kwargs):
        self.events.append("update_domain_nameservers")

    def update_domain_contact(self, *args, **kwargs):
        self.events.append("update_domain_contact")

    def enable_domain_auto_renew(self, *args, **kwargs):
        self.events.append("enable_domain_auto_renew")

    def disable_domain_auto_renew(self, *args, **kwargs):
        self.events.append("disable_domain_auto_renew")

    def check_domain_transferability(self, **kwargs):
        pass

    def transfer_domain(self, **kwargs):
        self.events.append("transfer_domain")
        self.transfer_kwargs = kwargs


class DomainManagerRegisterFake(DomainManagerFake):
    """A fake that reports the domain as not yet owned and available, so
    create_or_update follows the registration path."""

    def list_domains(self, **kwargs):
        return {'Domains': []}

    def check_domain_availability(self, *args, **kwargs):
        return {'Availability': 'AVAILABLE'}


class DomainManagerTransferFake(DomainManagerFake):
    """A fake that reports the domain as not yet owned but transferable, so
    create_or_update follows the transfer path."""

    def list_domains(self, **kwargs):
        return {'Domains': []}

    def check_domain_transferability(self, **kwargs):
        return {'Transferability': {'Transferable': 'TRANSFERABLE'}}


def _contact():
    return {
        'firstName': "Joe",
        'lastName': "Bob",
        'type': "PERSON",
        'phoneNumber': "+1.3035551212",
        'email': "joe@bob.com",
        'addressLine1': "PO Box 123",
        'city': "Nowhere",
        'state': "CA",
        'countryCode': "US",
        'zipCode': "91222"
    }


def test_exists():
    event = {
        'ResourceProperties': {
            'DomainName': "foo.com",
            'Contact': _contact(),
            'AutoRenew': 'true'
        }
    }

    index.domain_manager = DomainManagerFake()

    response = index.create_or_update(event, None)
    assert response == "foo.com"
    assert "register_domain" not in index.domain_manager.events
    assert "transfer_domain" not in index.domain_manager.events


def test_register_default_duration():
    """When DurationInYears is not provided, registration uses 1 year."""
    event = {
        'ResourceProperties': {
            'DomainName': "newdomain.com",
            'Contact': _contact(),
            'AutoRenew': 'true'
        }
    }

    index.domain_manager = DomainManagerRegisterFake()

    response = index.create_or_update(event, None)
    assert response == "newdomain.com"
    assert "register_domain" in index.domain_manager.events
    assert index.domain_manager.register_kwargs['DurationInYears'] == 1


def test_register_custom_duration():
    """When DurationInYears is provided, registration uses that value
    (e.g. 2 years for .ai)."""
    event = {
        'ResourceProperties': {
            'DomainName': "newdomain.ai",
            'Contact': _contact(),
            'AutoRenew': 'true',
            'DurationInYears': 2
        }
    }

    index.domain_manager = DomainManagerRegisterFake()

    response = index.create_or_update(event, None)
    assert response == "newdomain.ai"
    assert "register_domain" in index.domain_manager.events
    assert index.domain_manager.register_kwargs['DurationInYears'] == 2


def test_register_custom_duration_as_string():
    """CloudFormation may pass numeric properties as strings; the resource
    must coerce them to int."""
    event = {
        'ResourceProperties': {
            'DomainName': "newdomain.ai",
            'Contact': _contact(),
            'AutoRenew': 'true',
            'DurationInYears': "3"
        }
    }

    index.domain_manager = DomainManagerRegisterFake()

    index.create_or_update(event, None)
    assert index.domain_manager.register_kwargs['DurationInYears'] == 3


def test_transfer_custom_duration():
    """When DurationInYears is provided on a transfer, that value is used."""
    event = {
        'ResourceProperties': {
            'DomainName': "newdomain.ai",
            'Contact': _contact(),
            'AutoRenew': 'true',
            'TransferAuthCode': "abc123",
            'DurationInYears': 2
        }
    }

    index.domain_manager = DomainManagerTransferFake()

    index.create_or_update(event, None)
    assert "transfer_domain" in index.domain_manager.events
    assert index.domain_manager.transfer_kwargs['DurationInYears'] == 2


def test_update_missing_domain_is_noop():
    """On Update for a domain that's no longer in the account (e.g. it
    expired), the resource should not try to re-register it. It should
    just return success."""
    event = {
        'RequestType': 'Update',
        'ResourceProperties': {
            'DomainName': "expired.com",
            'Contact': _contact(),
            'AutoRenew': 'false'
        }
    }

    # RegisterFake reports the domain as not in the account but available;
    # without the no-op guard, the code would call register_domain.
    index.domain_manager = DomainManagerRegisterFake()

    response = index.create_or_update(event, None)
    assert response == "expired.com"
    assert "register_domain" not in index.domain_manager.events
    assert "transfer_domain" not in index.domain_manager.events


def test_create_missing_domain_still_registers():
    """The Update no-op must NOT apply to Create - new domains should still
    be registered."""
    event = {
        'RequestType': 'Create',
        'ResourceProperties': {
            'DomainName': "fresh.com",
            'Contact': _contact(),
            'AutoRenew': 'true'
        }
    }

    index.domain_manager = DomainManagerRegisterFake()

    response = index.create_or_update(event, None)
    assert response == "fresh.com"
    assert "register_domain" in index.domain_manager.events


def test_register_with_nameservers_waits_before_update():
    """A fresh registration that also sets nameservers must wait for the
    async registration operation to complete before calling
    UpdateDomainNameservers - otherwise the domain is "not found in account"."""
    event = {
        'RequestType': 'Create',
        'ResourceProperties': {
            'DomainName': "cimd.now",
            'Contact': _contact(),
            'AutoRenew': 'true',
            'NameServers': ['ns-1.example.com', 'ns-2.example.com']
        }
    }

    index.domain_manager = DomainManagerRegisterFake()

    response = index.create_or_update(event, None)
    assert response == "cimd.now"

    events = index.domain_manager.events
    # register, then poll the operation, then (only after) update nameservers
    assert events.index("register_domain") < events.index("get_operation_detail")
    assert events.index("get_operation_detail") < events.index("update_domain_nameservers")


def test_register_without_nameservers_does_not_wait():
    """No nameservers to set => no need to wait for the operation."""
    event = {
        'RequestType': 'Create',
        'ResourceProperties': {
            'DomainName': "newdomain.com",
            'Contact': _contact(),
            'AutoRenew': 'true'
        }
    }

    index.domain_manager = DomainManagerRegisterFake()

    index.create_or_update(event, None)
    assert "register_domain" in index.domain_manager.events
    assert "get_operation_detail" not in index.domain_manager.events
    assert "update_domain_nameservers" not in index.domain_manager.events


def test_wait_for_operation_polls_until_successful():
    """wait_for_operation keeps polling through non-terminal states."""
    statuses = iter([
        {'Status': 'SUBMITTED'},
        {'Status': 'IN_PROGRESS'},
        {'Status': 'SUCCESSFUL'},
    ])

    manager = DomainManagerFake()
    manager.get_operation_detail = lambda operation_id: next(statuses)

    # sleep is injected as a no-op so the test doesn't actually block
    manager.wait_for_operation("op-1", sleep=lambda _: None)
    # reaching here without raising means it succeeded


def test_wait_for_operation_raises_on_failure():
    manager = DomainManagerFake()
    manager.get_operation_detail = lambda operation_id: {'Status': 'ERROR'}

    with pytest.raises(Exception):
        manager.wait_for_operation("op-1", sleep=lambda _: None)


def test_wait_for_operation_times_out():
    manager = DomainManagerFake()
    manager.get_operation_detail = lambda operation_id: {'Status': 'IN_PROGRESS'}

    with pytest.raises(Exception):
        manager.wait_for_operation(
            "op-1", timeout_seconds=10, poll_interval_seconds=5, sleep=lambda _: None
        )


def test_delete_is_noop():
    """Delete must never call AWS - the domain must remain registered.
    We just stop tracking it in CloudFormation."""
    event = {
        'RequestType': 'Delete',
        'ResourceProperties': {
            'DomainName': "donotdelete.com",
            'Contact': _contact(),
            'AutoRenew': 'true'
        }
    }

    index.domain_manager = DomainManagerFake()

    response = index.delete(event, None)
    assert response == "donotdelete.com"
    # No AWS-mutating call of any kind.
    assert index.domain_manager.events == []


def test_live_create_unavailable():
    event = {
        'ResourceProperties': {
            'DomainName': "foo.com",
            'Contact': _contact(),
            'AutoRenew': 'true'
        }
    }

    index.domain_manager = DomainManagerLive()

    with pytest.raises(Exception):
        index.create_or_update(event, None)
