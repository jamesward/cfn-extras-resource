"""Custom CloudFormation resource handlers, one module per resource.

Each module exposes a Lambda ``handler(event, context)`` entrypoint, so a
single built artifact can back every resource - the Lambda for each resource
just points its ``Handler`` at ``cfn_extras.<module>.handler``.
"""
