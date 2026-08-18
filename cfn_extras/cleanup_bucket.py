from __future__ import print_function

from crhelper import CfnResource
import logging
import boto3

logger = logging.getLogger(__name__)

helper = CfnResource(json_logging=False, log_level='DEBUG', boto_level='CRITICAL', ssl_verify=None)


@helper.create
@helper.update
def create_or_update(event, context):
    # Nothing to do until delete; identify the resource by its bucket.
    return event['ResourceProperties']['BucketName']


@helper.delete
def delete(event, context):
    # Empty the bucket (including all object versions) so CloudFormation can
    # delete the AWS::S3::Bucket, which refuses to delete a non-empty bucket.
    bucket_name = event['ResourceProperties']['BucketName']
    bucket = boto3.resource('s3').Bucket(bucket_name)
    bucket.object_versions.all().delete()
    bucket.objects.all().delete()
    return bucket_name


def handler(event, context):
    helper(event, context)
