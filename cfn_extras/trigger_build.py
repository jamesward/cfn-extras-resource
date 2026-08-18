from __future__ import print_function

from crhelper import CfnResource
import logging
import time
import boto3

logger = logging.getLogger(__name__)

# No sleep_on_delete: this resource blocks while polling the build, so the
# Lambda timeout must comfortably exceed the build duration.
helper = CfnResource(json_logging=False, log_level='DEBUG', boto_level='CRITICAL', ssl_verify=None)

TERMINAL_FAILURES = ('FAILED', 'FAULT', 'STOPPED', 'TIMED_OUT')


@helper.create
@helper.update
def create_or_update(event, context):
    """Start the named CodeBuild project and block until it finishes.

    Used to run a one-shot build on deploy (e.g. publish a static site, or
    bootstrap a Lambda's code zip). Polls in-invocation, so the Lambda timeout
    must be long enough for the build.
    """
    codebuild = boto3.client('codebuild')
    build = codebuild.start_build(
        projectName=event['ResourceProperties']['ProjectName']
    )
    build_id = build['build']['id']

    while True:
        # Leave a buffer so we can fail cleanly rather than being killed
        # mid-poll by the Lambda timeout.
        if context is not None and context.get_remaining_time_in_millis() < 10000:
            raise Exception("Lambda timeout approaching before build completion")

        builds = codebuild.batch_get_builds(ids=[build_id])['builds']
        if not builds:
            raise Exception(f"Build {build_id} not found")

        status = builds[0]['buildStatus']

        if status == 'SUCCEEDED':
            helper.Data['BuildId'] = build_id
            helper.Data['Status'] = status
            return build_id

        if status in TERMINAL_FAILURES:
            logs = builds[0].get('logs', {})
            log_url = logs.get('deepLink', 'No logs URL available')
            phase = next((p for p in builds[0].get('phases', [])
                          if p.get('phaseStatus') == 'FAILED'), {})
            raise Exception(
                f"Build failed with status: {status}. "
                f"Phase: {phase.get('phaseType', 'Unknown')}. "
                f"Error: {phase.get('statusMessage', 'No error message available')}. "
                f"Logs: {log_url}"
            )

        # Still in progress; wait before polling again.
        time.sleep(10)


@helper.delete
def delete(event, context):
    # No-op: triggering a build owns nothing to tear down.
    return None


def handler(event, context):
    helper(event, context)
