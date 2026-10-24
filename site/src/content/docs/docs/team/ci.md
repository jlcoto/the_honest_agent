---
title: Run it in GitHub Actions
description: A workflow that runs the evals, keeps the results in S3, publishes the report and sends the alert.
---

:::caution[An example, not a security review]
This is one setup we tested, shown as an example. Don't copy it blindly: check each step
against your company's security policies, and adapt it before you use it with real data.
See [Your setup, your responsibility](/docs/team/#your-setup-your-responsibility).
:::

This workflow runs your evals, keeps the results in S3, publishes the report to Cloudflare
Pages (or AWS, in the [variant](#variant-report-on-aws)), and sends the Slack alert.

It assumes you've set up:

- [results in S3](/docs/team/results-s3/);
- the report on [Cloudflare](/docs/team/report-cloudflare/) or [AWS](/docs/team/report-aws/);
- a [Slack webhook](/docs/alerts/).

:::note[What was tested]
Tested on 2026-10-08, started by hand (`workflow_dispatch`): four runs with the report on
Cloudflare, one with the report on AWS. Each run added to the history without
duplicates, the report deployed, and Slack posted only when an eval fell below its
threshold. *Not tested yet:* a schedule, the steps that keep going after `run` exits
with 1 (added on 2026-10-12), the download step that starts a new history when there
is no results file yet (added on 2026-10-13), and the target's URL variable (added on
2026-10-18). Results in MotherDuck aren't covered by this recipe.
:::

:::caution[Use a private repository]
Workflow logs show your agent's answers and errors.
:::

## 1. Let GitHub Actions use the role

GitHub Actions gets into AWS with short-lived credentials (OpenID Connect), not stored
keys. It takes the [results role](/docs/team/results-s3/#4-create-a-role-with-that-policy)
you created for S3.

**Add GitHub as an identity provider first:** IAM → Identity providers → Add provider →
OpenID Connect, URL `https://token.actions.githubusercontent.com`, audience
`sts.amazonaws.com`. IAM may reject a trust policy that names a provider that doesn't
exist yet. An account has only one per URL: reuse it if it's there.

**Find your repository's subject prefix.** GitHub sends it in one of two formats, and the
trust policy must match it exactly:

```bash
gh api repos/<owner>/<repo>/actions/oidc/customization/sub    # the sub_claim_prefix field
```

- classic: `repo:<owner>/<repo>`;
- immutable: `repo:<owner>@<owner_id>/<repo>@<repo_id>`. It's safer: a deleted
  repository recreated under the same name can't use the role.

**Change the role's trust policy:** IAM → Roles → *your role* → **Trust relationships** →
Edit trust policy. (Not the permissions policy: a `Principal` there is rejected as
"Unsupported Principal".) Replace the local-testing statement with:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "GitHubActions",
      "Effect": "Allow",
      "Principal": { "Federated": "arn:aws:iam::<account-id>:oidc-provider/token.actions.githubusercontent.com" },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
          "token.actions.githubusercontent.com:sub": "<sub_claim_prefix>:ref:refs/heads/main"
        }
      }
    }
  ]
}
```

A mismatch fails with `Not authorized to perform sts:AssumeRoleWithWebIdentity`.
CloudTrail's `AssumeRoleWithWebIdentity` events show the subject GitHub actually sent.
The permissions policy stays as it is: read and write the results file, and list the
bucket.

**Check the bucket's region.** Bucket names are global, but each bucket lives in one
region, and `AWS_REGION` must be that one: `aws s3api head-bucket --bucket <bucket>`
(the `BucketRegion` field).

## 2. Create a Cloudflare deploy token

My Profile → API Tokens → Create Token → Custom: the permission **Account → Cloudflare
Pages → Edit**, limited to your account.

Every CI deploy creates a preview address (`<hash>.<project>.pages.dev`,
`main.<project>.pages.dev`), so check that Access covers those too, not only the main
address (the `*` subdomain in [step 4](/docs/team/report-cloudflare/#4-create-the-access-application)).

## 3. Add the variables and secrets

**Variables** aren't secret: `gh variable set NAME -R <owner>/<repo> --body <value>`.

| Name | Value |
|---|---|
| `AWS_REGION` | the results bucket's region |
| `AWS_ROLE_ARN` | `arn:aws:iam::<account-id>:role/<role>` |
| `RESULTS_S3` | `s3://<bucket>/results/results.duckdb.gz` |
| `HONEST_AGENT_REPORT_URL` | `https://<project>.pages.dev/` |
| `CLOUDFLARE_ACCOUNT_ID` | your Cloudflare account ID (in `.wrangler/cache/wrangler-account.json` after a deploy from your machine) |
| your target's URL variable | the server's URL, as in `.env`: the variable your target's `mcp_url` reads with `env_var()`, e.g. `SNOWFLAKE_MCP_URL`. `init` always writes the URL this way. |

**Secrets:** `gh secret set NAME -R <owner>/<repo>` prompts for the value without
showing it. Never use `--body` for a secret: it stays in your shell history. The prompt
needs a real terminal; without one, read the value from `.env`:
`grep "^NAME=" .env | cut -d= -f2- | gh secret set NAME -R <owner>/<repo>`.

| Name | What |
|---|---|
| `ANTHROPIC_API_KEY` | the model's API key (or `OPENAI_API_KEY`) |
| your target's token | the variable your target's `bearer_token_env` names, read-only; add any `mcp_env` variables too |
| `CLOUDFLARE_API_TOKEN` | the deploy token from step 2 |
| `SLACK_WEBHOOK_URL` | the Slack webhook |

**Snowflake target?** Its network policy must also let GitHub's runners in, or `run` can't
connect. See [Running in GitHub Actions](/docs/connect/snowflake/#running-in-github-actions).

## 4. Add the workflow

Save this as `.github/workflows/honest-agent.yml`, and fill in everything marked `<...>`.
Replace `<TARGET_URL_ENV>` and `<TARGET_TOKEN_ENV>` with your target's URL and token
variables, and set the schedule: `cron` uses UTC, and scheduled runs start from your
default branch. Each run calls the model for every eval, so pick a schedule that fits your
budget.

```yaml
name: honest-agent

on:
  schedule:
    - cron: "0 6 * * *"   # every day at 06:00 UTC; change to the schedule you want
  workflow_dispatch:      # and a "Run workflow" button, to start it by hand

permissions:
  id-token: write   # GitHub OIDC -> AWS
  contents: read

# Only one job may touch the results file at a time.
concurrency:
  group: honest-agent-results
  cancel-in-progress: false

defaults:
  run:
    shell: bash     # adds pipefail, so a failure inside a pipe fails the step

jobs:
  evals:
    runs-on: ubuntu-latest   # has the AWS CLI and Node
    env:
      RESULTS_S3: ${{ vars.RESULTS_S3 }}
      HONEST_AGENT_TARGET: <target>               # a target in honest_agent_config.yml
      <TARGET_URL_ENV>: ${{ vars.<TARGET_URL_ENV> }}   # run and notify both read it
      CLOUDFLARE_PAGES_PROJECT: <pages-project>
    steps:
      - uses: actions/checkout@v4

      - uses: astral-sh/setup-uv@v6

      - name: Install honest-agent
        run: uv tool install "git+https://github.com/jlcoto/the_honest_agent@v0.2.0#subdirectory=cli"

      - uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ vars.AWS_ROLE_ARN }}
          aws-region: ${{ vars.AWS_REGION }}

      - name: Check AWS identity
        run: aws sts get-caller-identity

      # A missing file (404) starts a new history; any other error stops the job
      # before anything is overwritten. See "Store results in S3".
      - name: Download results
        id: download
        run: |
          bucket=${RESULTS_S3#s3://}; key=${bucket#*/}; bucket=${bucket%%/*}
          mkdir -p honest_agent_results
          if found=$(aws s3api head-object --bucket "$bucket" --key "$key" 2>&1); then
            aws s3 cp "$RESULTS_S3" results.duckdb.gz
            gunzip -t results.duckdb.gz
            gunzip -c results.duckdb.gz > honest_agent_results/results.duckdb
          elif [[ $found == *"(404)"* ]]; then
            echo "No results file in S3 yet: this run starts a new history."
          else
            echo "$found" >&2
            exit 1
          fi

      # Exits 1 when an eval falls below its threshold, which marks the job as
      # failed; the steps after it still run (`!cancelled()`), so the report is
      # published and `notify` sends the alert.
      - name: Run evals
        run: honest-agent run --target "$HONEST_AGENT_TARGET"
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          <TARGET_TOKEN_ENV>: ${{ secrets.<TARGET_TOKEN_ENV> }}

      # Save results even if a later step fails, but never when the download failed,
      # and only if there's a file to save (a first run that failed early has none).
      - name: Upload results
        if: always() && steps.download.outcome == 'success' && hashFiles('honest_agent_results/results.duckdb') != ''
        run: gzip -c honest_agent_results/results.duckdb | aws s3 cp - "$RESULTS_S3"

      - name: Build report
        id: build
        if: ${{ !cancelled() && steps.download.outcome == 'success' }}
        run: honest-agent report

      - name: Deploy report
        if: ${{ !cancelled() && steps.build.outcome == 'success' }}
        run: npx --yes wrangler pages deploy honest_agent_report --project-name "$CLOUDFLARE_PAGES_PROJECT" --branch main
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ vars.CLOUDFLARE_ACCOUNT_ID }}

      - name: Notify Slack
        if: ${{ !cancelled() && steps.download.outcome == 'success' }}
        run: honest-agent notify --target "$HONEST_AGENT_TARGET"
        env:
          SLACK_WEBHOOK_URL: ${{ secrets.SLACK_WEBHOOK_URL }}
          HONEST_AGENT_REPORT_URL: ${{ vars.HONEST_AGENT_REPORT_URL }}
```

A few things about it:

- **It installs honest-agent with `uv tool install`,** a global install, because a CI job
  has no project to add it to. Pin the version you tested, as above.
- **The download only starts a new history when S3 says the file doesn't exist** (404).
  Any other error, like a permission problem, stops the job before anything is
  overwritten. This needs the bucket listing permission from
  [Store results in S3](/docs/team/results-s3/#3-create-a-policy-for-the-one-file).
- **GitHub warns that these action versions run on Node 20.** Pin newer major versions
  when they're available.

Run it, then follow it:

```bash
gh workflow run honest-agent.yml -R <owner>/<repo>
gh run watch <run-id> -R <owner>/<repo>       # the run ID is required when not interactive
```

Add `.env`, `*.duckdb`, `*.duckdb.gz`, `honest_agent_results/`, `honest_agent_report/`,
`.venv/` and `.wrangler/` to the repository's `.gitignore`.

## Variant: report on AWS

The same workflow, with the report going to the [AWS stack](/docs/team/report-aws/)'s
bucket instead of Cloudflare, then CloudFront's cache cleared. The results, role and
trust policy stay the same. Both workflows can live in one repository: they share the
`concurrency` group, so they never write the results file at the same time.

**Read the stack's outputs by name.** `describe-stacks` prints every output, including
the Cognito client secret (and searching for "secret" misses it: the name and the value
can be on different lines). Ask only for what you need, in the stack's region:

```bash
aws cloudformation describe-stacks --region <region> --stack-name serverlessrepo-honest-agent-report-auth \
  --query "Stacks[0].Outputs[?OutputKey=='S3Bucket'||OutputKey=='CloudFrontDistribution'||OutputKey=='WebsiteUrl']"
```

**Give the role three more permissions:** IAM → Roles → *your role* → **Permissions** →
Add permissions → Create inline policy → JSON. The trust policy doesn't change.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ListReportBucket",
      "Effect": "Allow",
      "Action": "s3:ListBucket",
      "Resource": "arn:aws:s3:::<report-bucket>"
    },
    {
      "Sid": "WriteReportFiles",
      "Effect": "Allow",
      "Action": ["s3:PutObject", "s3:DeleteObject"],
      "Resource": "arn:aws:s3:::<report-bucket>/*"
    },
    {
      "Sid": "InvalidateReportCache",
      "Effect": "Allow",
      "Action": "cloudfront:CreateInvalidation",
      "Resource": "arn:aws:cloudfront::<account-id>:distribution/<distribution-id>"
    }
  ]
}
```

`s3 sync` needs the listing, and `--delete` needs the delete. Because of `--delete`, the
bucket must hold nothing but the report; the stack's bucket doesn't. Its encryption
(SSE-S3) needs no KMS permissions; a bucket of your own with SSE-KMS would also need
`kms:GenerateDataKey` on its key.

**Variables,** on top of the ones above:

| Name | Value |
|---|---|
| `REPORT_S3_BUCKET` | the stack output `S3Bucket`, without `s3://` |
| `REPORT_S3_REGION` | the stack's region (it can differ from `AWS_REGION`) |
| `CLOUDFRONT_DISTRIBUTION_ID` | the stack output `CloudFrontDistribution` |
| `HONEST_AGENT_REPORT_URL` | the stack output `WebsiteUrl`, plus `/` |

No Cloudflare secrets are needed.

**The workflow** `.github/workflows/honest-agent-s3.yml`: the same as above up to
**Build report**. Add the variables to the job's `env:` and replace the last three steps:

```yaml
    env:
      RESULTS_S3: ${{ vars.RESULTS_S3 }}
      HONEST_AGENT_TARGET: <target>
      <TARGET_URL_ENV>: ${{ vars.<TARGET_URL_ENV> }}
      REPORT_S3_BUCKET: ${{ vars.REPORT_S3_BUCKET }}
      REPORT_S3_REGION: ${{ vars.REPORT_S3_REGION }}
      CLOUDFRONT_DISTRIBUTION_ID: ${{ vars.CLOUDFRONT_DISTRIBUTION_ID }}
    steps:
      # ... checkout, install, AWS login, download, run, upload, build report as above ...

      # --delete removes old hashed assets.
      - name: Deploy report to S3
        id: deploy
        if: ${{ !cancelled() && steps.build.outcome == 'success' }}
        run: aws s3 sync honest_agent_report/ "s3://$REPORT_S3_BUCKET/" --delete --region "$REPORT_S3_REGION"

      # Drop CloudFront's cached copy so the new report is served right away.
      - name: Invalidate CloudFront
        if: ${{ !cancelled() && steps.deploy.outcome == 'success' }}
        run: aws cloudfront create-invalidation --distribution-id "$CLOUDFRONT_DISTRIBUTION_ID" --paths '/*' --query 'Invalidation.{id:Id,status:Status}' --output text

      - name: Notify Slack
        if: ${{ !cancelled() && steps.download.outcome == 'success' }}
        run: honest-agent notify --target "$HONEST_AGENT_TARGET"
        env:
          SLACK_WEBHOOK_URL: ${{ secrets.SLACK_WEBHOOK_URL }}
          HONEST_AGENT_REPORT_URL: ${{ vars.HONEST_AGENT_REPORT_URL }}
```

`/*` counts as one path toward CloudFront's 1,000 free invalidation paths a month.

**Recommended** (each part tested, not yet together in CI): the invalidation refreshes
CloudFront, but without a cache header, browsers may keep an old `index.html` or
`report.json` for a while. Upload those two with `no-cache`, as in
[Host the report on AWS](/docs/team/report-aws/#3-upload-the-report):

```bash
aws s3 sync honest_agent_report/ "s3://$REPORT_S3_BUCKET/" --delete --region "$REPORT_S3_REGION" --exclude "index.html" --exclude "data/*"
aws s3 cp honest_agent_report/index.html "s3://$REPORT_S3_BUCKET/index.html" --cache-control no-cache --region "$REPORT_S3_REGION"
aws s3 cp honest_agent_report/data/ "s3://$REPORT_S3_BUCKET/data/" --recursive --cache-control no-cache --region "$REPORT_S3_REGION"
```

With these, CloudFront also checks for a new version on every load, so the invalidation
becomes optional.

**After the first run, check** that `curl -sI https://<id>.cloudfront.net/` answers `307`
to `*.amazoncognito.com`, that a direct S3 address for a file answers `403`, and that
signing in shows the new run.
