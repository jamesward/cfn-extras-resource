# Developing cfn-extras-resource

Custom CloudFormation resource handlers, consolidated into a single Python
package. This replaces the former one-repo-per-resource layout
(`cfn-domain-resource`, `cfn-hostedzone-resource`, `cfn-connectionlookup-resource`)
and the inline scripts that used to live in `cfn-pkl-extras/src/resources`.

## Layout

Everything is one package, `cfn_extras`, with one module per resource. Each
module exposes a Lambda `handler(event, context)`, so a single built artifact
can back every resource — each Lambda just points its `Handler` at the right
module (`cfn_extras.domain.handler`, `cfn_extras.connection_lookup.handler`, …).

```
cfn_extras/            # the handlers, one module per resource
infra/infra.pkl        # Pkl source for the release infra (bucket + CodeBuild)
infra/infra.yaml       # generated template, deployed via Git sync
infra/deploy.yaml      # Git sync deployment file (supplies ConnectionArn)
scripts/build_zip.sh   # builds the slim Lambda deployment package
buildspec.yml          # what CodeBuild runs on each tag
tests/                 # pytest suite
```

All handlers use [`crhelper`](https://github.com/aws-cloudformation/custom-resource-helper)
for the CloudFormation response lifecycle. `boto3`/`botocore` are provided by the
Lambda runtime and are deliberately **not** bundled — a bundled (older) copy
would shadow the runtime SDK and break newer services such as `codeconnections`.

## Develop / test

```
nix-shell            # or: python -m venv venv && source venv/bin/activate
pip install -r requirements-dev.txt
pytest
```

`requirements.txt` is the runtime dependency set that gets bundled (just
`crhelper`). `requirements-dev.txt` adds a current `boto3` (so the handlers
import and tests can exercise a modern SDK) and `pytest`.

## Building the artifact

```
PYTHON=./venv/bin/python ./scripts/build_zip.sh   # or just ./scripts/build_zip.sh where pip is on PATH
```

`build_zip.sh` produces a **slim, deterministic** zip (`dist/cfn-extras-resource.zip`,
~16 KB): the `cfn_extras` package plus `crhelper` only. It installs runtime deps
with `--no-deps` (keeping `boto3`/`botocore` out) and strips tests, caches,
`*.dist-info`, and type stubs. Entries are written sorted with fixed timestamps,
so identical inputs yield byte-identical artifacts.

## Releasing

Releases are built by the CodeBuild project (provisioned by the infra stack
below), not by GitHub Actions. Pushing a `v*` tag fires the project's webhook,
which runs `buildspec.yml`:

1. Builds the slim zip (`scripts/build_zip.sh`).
2. Uploads it to a **single stable key**, `s3://<bucket>/cfn-extras-resource.zip`.
   Because the bucket is versioned, each release is a new S3 **object version** —
   the key never changes; the release identity is the `S3ObjectVersion`.
3. Writes a `versions/<tag>.json` pointer recording the `S3ObjectVersion` for
   that tag, so consumers can look up which version to pin.

```
git tag v1.2.3
git push origin v1.2.3
```

This CodeBuild only *builds the artifact* in the owner's account. Consumers
don't touch CodeBuild — they just reference the S3 object.

## Release infrastructure (Git sync)

`infra/infra.pkl` renders one CloudFormation stack containing:

- the public, versioned artifact bucket (+ public-read bucket policy),
- an IAM role for CodeBuild, and
- the CodeBuild project with a webhook filtered to `^refs/tags/v.*`.

The stack is deployed via **CloudFormation Git sync** from this repo, so a
committed template change updates the infra automatically. Two files are
committed:

- `infra/infra.yaml` — the template. Regenerate after editing `infra.pkl`:
  ```
  cd infra && pkl project resolve && pkl eval infra.pkl -f yaml -o infra.yaml
  ```
- `infra/deploy.yaml` — the Git sync deployment file; supplies the parameters.

`ConnectionArn` is a stack **parameter** (not baked into the template) so it's
provided at sync time via `infra/deploy.yaml`. Point it at a CodeConnections
connection authorized for this GitHub account (any standard region works — e.g.
an existing us-west-2 connection; CodeBuild can use it cross-region).

### Setting up the sync (one time)

1. Push this repo to GitHub.
2. Set `infra/deploy.yaml`'s `ConnectionArn` (or leave it and enter the value in
   the console — Git sync can generate the deployment file for you).
3. In the CloudFormation console, create a stack with **Sync from Git**:
   - stack name e.g. `cfn-extras-resource-artifacts`;
   - repository `jamesward/cfn-extras-resource` and your branch;
   - deployment file `infra/deploy.yaml`;
   - a CodeConnections connection to the repo (can be the same one used for
     `ConnectionArn`);
   - a deployment IAM role (below), acknowledging `CAPABILITY_IAM`.
4. Merge the PR Git sync opens. Thereafter, pushing a `v*` tag triggers the
   CodeBuild project to build and publish the artifact.

### Prerequisites

- **A CodeConnections connection** authorized for the GitHub account — used as
  the `ConnectionArn` parameter (CodeBuild source) and, optionally, as the repo
  connection Git sync monitors. Any standard region.
- **A Git sync deployment IAM role** allowed to create/update the stack's
  resources: the S3 bucket + bucket policy + public-access-block, the CodeBuild
  IAM role (so `CAPABILITY_IAM` plus `iam:CreateRole`/`PutRolePolicy`/`PassRole`),
  and the CodeBuild project. The console can create this role for you.
- **Account-level S3 Block Public Access** must allow public bucket policies
  (`BlockPublicPolicy` and `RestrictPublicBuckets` off for the account), since
  the bucket is intentionally public-read.

### Cost / availability note

The bucket is public-read, so you (the owner) pay the S3 GET/transfer costs for
everyone who uses it, and you are their availability dependency: in `REFERENCE`
mode a referenced object version must stay present, so **don't delete an object
version that a release still points at** — consumers' functions would drop to
`Inactive` on their next cold start.
