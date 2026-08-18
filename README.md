# cfn-extras-resource

A small set of custom CloudFormation resources for things CloudFormation can't
do natively — registering Route 53 domains, resolving the CodeConnections ARN
behind a Git-sync stack, emptying buckets/hosted zones on delete, calling an
arbitrary AWS SDK method, and more.

All of them ship as one tiny Lambda artifact published to a public, versioned
S3 bucket. Each resource is just a different `Handler` on that same artifact, so
you reference one zip and pick the entrypoint you need.

## Resources

| Resource | Handler | What it does |
|----------|---------|--------------|
| Domain | `cfn_extras.domain.handler` | Register/transfer a Route 53 domain and keep contact, auto-renew and nameservers in sync. Delete is a no-op (never de-registers a domain). |
| Connection lookup | `cfn_extras.connection_lookup.handler` | Resolve the CodeConnections ARN backing this stack's CloudFormation Git sync. Read it with `Fn::GetAtt <Resource>.ConnectionArn`. |
| Hosted zone manager | `cfn_extras.hosted_zone.handler` | On delete, remove all non-NS/SOA records so an `AWS::Route53::HostedZone` can be deleted. |
| SDK call | `cfn_extras.sdk_call.handler` | Generic "call one AWS SDK method" resource (like CDK's `AwsCustomResource`). Flattens the response for `Fn::GetAtt` and can take its physical id from a response path. |
| Trigger build | `cfn_extras.trigger_build.handler` | Start a CodeBuild project on deploy and wait for it to finish. |
| Cleanup bucket | `cfn_extras.cleanup_bucket.handler` | On delete, empty an S3 bucket (including versions) so it can be deleted. |

## Using it

Each resource is an `AWS::Lambda::Function` plus an
`AWS::CloudFormation::CustomResource` that invokes it. Point the function at the
published artifact using Lambda self-managed S3 code storage
(`S3ObjectStorageMode: REFERENCE`). The artifact lives in one region but
`REFERENCE` mode lets it back Lambdas in any standard region, so the same public
bucket works everywhere.

The artifact is published to a single stable key; each release is a distinct S3
object version. Pick the release you want by its `S3ObjectVersion` — look up the
version for a tag at `s3://cfn-extras-resource/versions/<tag>.json`, e.g.:

```
aws s3 cp s3://cfn-extras-resource/versions/v1.2.3.json - --no-sign-request
# {"bucket":"cfn-extras-resource","key":"cfn-extras-resource.zip","s3ObjectVersion":"<id>","tag":"v1.2.3"}
```

Then:

```yaml
DomainFunction:
  Type: AWS::Lambda::Function
  Properties:
    Runtime: python3.13
    Handler: cfn_extras.domain.handler          # pick the resource you need
    Role: !GetAtt DomainRole.Arn
    Timeout: 600
    Code:
      S3Bucket: cfn-extras-resource
      S3Key: cfn-extras-resource.zip
      S3ObjectVersion: <s3ObjectVersion for the release>
      S3ObjectStorageMode: REFERENCE

foocomDomain:
  Type: AWS::CloudFormation::CustomResource
  Properties:
    ServiceToken: !GetAtt DomainFunction.Arn
    DomainName: foo.com
    Contact:
      firstName: Joe
      lastName: Bob
      type: PERSON
      addressLine1: PO Box 123
      city: Nowhere
      state: CA
      countryCode: US
      zipCode: '91234'
      phoneNumber: '+1.8055551212'
      email: joe@bob.com
    NameServers: !GetAtt foocomHostedZone.NameServers
    AutoRenew: true
```

The function's execution role needs whatever AWS permissions that resource
uses (e.g. `route53domains:*` for Domain, `route53` record changes for the
hosted zone manager, `codeconnections:GetSyncConfiguration`/`GetRepositoryLink`
for connection lookup).

If you use [Pkl](https://pkl-lang.org) for your CloudFormation,
[`cfn-pkl-extras`](https://github.com/jamesward/cfn-pkl-extras) wires these
resources up for you.

## Contributing

See [DEV.md](DEV.md) for project layout, building, testing, and how releases
are cut.
