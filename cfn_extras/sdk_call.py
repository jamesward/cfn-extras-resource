from __future__ import print_function

from crhelper import CfnResource
import logging
import boto3

logger = logging.getLogger(__name__)

helper = CfnResource(json_logging=False, log_level='DEBUG', boto_level='CRITICAL', ssl_verify=None)


def flatten(obj, prefix, out):
    """Flatten a nested response into dot-notation keys, e.g.
    {"A": {"B": "x"}} -> {"A.B": "x"}.

    CloudFormation custom-resource Fn::GetAtt does a flat key lookup (it can't
    traverse nested JSON), so the dot key becomes the attribute name:
    Fn::GetAtt [Resource, "A.B"].
    """
    if isinstance(obj, dict):
        for k, v in obj.items():
            flatten(v, prefix + k + ".", out)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            flatten(v, prefix + str(i) + ".", out)
    else:
        out[prefix[:-1]] = obj if isinstance(obj, str) else str(obj)


def dig(obj, path):
    """Follow a dot path into a nested response, indexing into lists by number."""
    for part in path.split("."):
        obj = obj[int(part)] if isinstance(obj, list) else obj[part]
    return obj


def call(props):
    """Make one boto3 SDK call described by the resource properties and return
    ``(data, physical_id)``.

    Properties:
      Service                 boto3 client name, e.g. "codeconnections"
      Action                  client method, e.g. "get_repository_link"
      Parameters              kwargs for the method (optional)
      PhysicalResourceIdPath  dot path into the response to use as the physical
                              id (optional; if absent, crhelper generates one)

    Pure except for the boto3 call, so tests can drive it with a fake client
    factory.
    """
    client = boto3.client(props["Service"])
    response = getattr(client, props["Action"])(**props.get("Parameters", {}))
    response.pop("ResponseMetadata", None)
    data = {}
    flatten(response, "", data)
    id_path = props.get("PhysicalResourceIdPath")
    physical_id = str(dig(response, id_path)) if id_path else None
    return data, physical_id


@helper.create
@helper.update
def create_or_update(event, context):
    data, physical_id = call(event["ResourceProperties"])
    helper.Data.update(data)
    # Returning None lets crhelper keep/generate the physical id.
    return physical_id


@helper.delete
def delete(event, context):
    # No-op: a read/one-shot SDK call owns nothing to tear down. Resources that
    # need cleanup should use a purpose-built handler.
    return None


def handler(event, context):
    helper(event, context)
