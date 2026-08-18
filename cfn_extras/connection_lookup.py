from __future__ import print_function

from abc import ABC, abstractmethod
from dataclasses import dataclass

from crhelper import CfnResource
import logging
import os
import boto3

logger = logging.getLogger(__name__)

helper = CfnResource(json_logging=False, log_level='DEBUG', boto_level='CRITICAL', ssl_verify=None)

# The only sync type CloudFormation Git sync registers. Kept as a constant
# rather than a bare string so it can't drift between the resolver and the
# event parser.
CFN_STACK_SYNC = 'CFN_STACK_SYNC'


@dataclass
class ConnectionLookupEvent:
    """The inputs needed to triangulate a stack's Git-sync connection.

    `stack_name` is normally wired to `Ref AWS::StackName` in the template, so
    the resource resolves the connection of the very stack it is part of.
    """
    stack_name: str
    sync_type: str = CFN_STACK_SYNC


class ConnectionResolver(ABC):
    """Boundary for the CodeConnections reads used during resolution.

    Modelled as an interface (rather than calling boto3 inline) so the pure
    resolution logic in `resolve_connection_arn` can be exercised with a fake
    in unit tests, with no live AWS calls.
    """

    @abstractmethod
    def get_sync_configuration(self, sync_type: str, resource_name: str) -> dict:
        pass

    @abstractmethod
    def get_repository_link(self, repository_link_id: str) -> dict:
        pass


class ConnectionResolverLive(ConnectionResolver):

    def __init__(self):
        # codeconnections is regional; AWS_REGION is always set in Lambda, and
        # we fall back to us-east-1 for local/test instantiation so importing
        # this module never raises NoRegionError.
        region = (
            os.environ.get('AWS_REGION')
            or os.environ.get('AWS_DEFAULT_REGION')
            or 'us-east-1'
        )
        self.client = boto3.client('codeconnections', region_name=region)

    def get_sync_configuration(self, sync_type: str, resource_name: str) -> dict:
        return self.client.get_sync_configuration(
            SyncType=sync_type,
            ResourceName=resource_name,
        )

    def get_repository_link(self, repository_link_id: str) -> dict:
        return self.client.get_repository_link(RepositoryLinkId=repository_link_id)


def resolve_connection_arn(resolver: ConnectionResolver, event: ConnectionLookupEvent) -> str:
    """Resolve the CodeConnections ARN backing a stack's Git sync.

        stack name
          --get_sync_configuration(CFN_STACK_SYNC)--> RepositoryLinkId
          --get_repository_link-------------------->  ConnectionArn

    This is deterministic and scoped to the deploying stack, so it does not
    depend on connection names or on there being exactly one connection in the
    account.
    """
    sync_configuration = resolver.get_sync_configuration(
        event.sync_type, event.stack_name
    ).get('SyncConfiguration', {})

    repository_link_id = sync_configuration.get('RepositoryLinkId')
    if not repository_link_id:
        raise Exception(
            f"No {event.sync_type} sync configuration found for stack "
            f"{event.stack_name!r}. Is this stack deployed via CloudFormation "
            "Git sync?"
        )

    repository_link_info = resolver.get_repository_link(
        repository_link_id
    ).get('RepositoryLinkInfo', {})

    connection_arn = repository_link_info.get('ConnectionArn')
    if not connection_arn:
        raise Exception(
            f"Repository link {repository_link_id!r} has no ConnectionArn"
        )

    return connection_arn


try:
    connection_resolver: ConnectionResolver = ConnectionResolverLive()
except Exception as e:
    helper.init_failure(e)


def parse_event(event) -> ConnectionLookupEvent:
    properties = event['ResourceProperties']
    return ConnectionLookupEvent(
        stack_name=properties['StackName'],
        sync_type=properties.get('SyncType', CFN_STACK_SYNC),
    )


@helper.create
@helper.update
def create_or_update(event, context):
    lookup_event = parse_event(event)
    connection_arn = resolve_connection_arn(connection_resolver, lookup_event)
    # Exposed for Fn::GetAtt <Resource>.ConnectionArn
    helper.Data['ConnectionArn'] = connection_arn
    # Using the ARN as the physical id keeps GetAtt stable and makes updates a
    # no-op when the resolved connection hasn't changed.
    return connection_arn


@helper.delete
def delete(event, context):
    # No-op: this resource only reads existing connection metadata, it never
    # creates or owns a connection, so there is nothing to tear down.
    return None


def handler(event, context):
    helper(event, context)
