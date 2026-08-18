from __future__ import print_function
from crhelper import CfnResource
import logging
import boto3

logger = logging.getLogger(__name__)

helper = CfnResource(json_logging=False, log_level='DEBUG', boto_level='CRITICAL', sleep_on_delete=120, ssl_verify=None)

try:
    route53 = boto3.client('route53')
    pass
except Exception as e:
    helper.init_failure(e)


@helper.create
@helper.update
def create_or_update(event, context):
    # Nothing to do on create/update: this resource only cleans up records at
    # delete time so the AWS::Route53::HostedZone can be deleted.
    return event.get('PhysicalResourceId') or event['LogicalResourceId']


@helper.delete
def delete(event, context):
    hosted_zone_id = event['ResourceProperties']['HostedZoneId']

    # Delete all records except NS/SOA so Route 53 will let the hosted zone be
    # deleted (it refuses while other records - e.g. an ACM validation CNAME -
    # remain). Paginated in case the zone holds more than one page of records.
    paginator = route53.get_paginator('list_resource_record_sets')
    for page in paginator.paginate(HostedZoneId=hosted_zone_id):
        for record in page['ResourceRecordSets']:
            if record['Type'] not in ['NS', 'SOA']:
                route53.change_resource_record_sets(
                    HostedZoneId=hosted_zone_id,
                    ChangeBatch={
                        'Changes': [{
                            'Action': 'DELETE',
                            'ResourceRecordSet': record
                        }]
                    }
                )


def handler(event, context):
    helper(event, context)
