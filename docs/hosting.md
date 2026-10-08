# Hosting honest-agent for a team

> **Draft.** Written from a from-scratch walkthrough on 2026-10-08. Parts marked
> *not tested yet* are plans, not verified steps.

> **Your setup, your responsibility.** This guide shows one way to host
> honest-agent that we tested. It is not a security review of your setup.
> You are responsible for checking every setting against your own
> infrastructure and policies: who can open the report, who can read and
> write the results, where your data is stored, and how credentials are
> handled. The report and the results contain your agent's tool output,
> which can include data from your warehouse. Treat them like that data.
> Cloud consoles change often, so menu names here may differ from what you
> see.

## What you are setting up

```
 CI job (scheduled)
 ┌───────────────────────────────────────────────────────────────┐
 │ 1. get results.duckdb       ◄── private storage (CI only)
 │ 2. honest-agent run
 │ 3. honest-agent report      ──► honest_agent_report/
 │ 4. deploy the report folder ──► static host behind sign-in ◄── your team
 │ 5. save results.duckdb      ──► private storage
 │ 6. honest-agent notify      ──► Slack, linking to the host
 └───────────────────────────────────────────────────────────────┘
```

Two things live in two places, on purpose:

- **The results database** holds everything: raw requests and responses,
  run settings, all history. Only the job that runs evals reads and writes
  it.
- **The report** is generated from it and shows recent results. Your team
  opens it in the browser, behind a sign-in. Viewers never get the
  database.

Never host the report publicly, and never expose `honest-agent serve`: it is
a local viewer with no sign-in.

## Part 1: where the results live

Pick one.

| Option | How | Good for |
|---|---|---|
| **MotherDuck** | `results_path: md:<name>`; honest-agent reads and writes it directly | Teams already on MotherDuck. Nothing to download, parallel jobs are fine |
| **A file in S3** | The job downloads `results.duckdb`, runs, and uploads it again | Teams that keep everything in their own AWS account |
| **A local file** | The default | One machine that always runs the evals |

### MotherDuck

1. Create a MotherDuck **service account** that holds only the results.
2. Put its read/write token in `HONEST_AGENT_RESULTS_TOKEN` (in `.env`
   locally, a secret in CI).
3. Set `results_path: md:honest_agent_results` in `honest_agent_config.yml`.
   The database is created on the first `run`.

Never use the agent's own `MOTHERDUCK_TOKEN` (the motherduck target's
read-only token) for the results: the agent being evaluated must not be able
to change its own results. honest-agent opens the results with
`HONEST_AGENT_RESULTS_TOKEN` only, even when `MOTHERDUCK_TOKEN` is also set.

### A file in S3

DuckDB can't write a database file that sits in S3, so the job copies it in
and out with the AWS CLI. Keep `results_path` a local file.

**1. Bucket** (S3 → Create bucket)

- A name you'll reuse below, e.g. `acme-honest-agent`.
- Block all public access: **on** (the default).
- Bucket Versioning: **Enable**. Every upload replaces the whole file, so a
  bad upload could wipe your history; versions let you restore it.
- Encryption: the default (SSE-S3).
- Use a separate bucket (or no bucket) for the report: the results should
  never be reachable by report viewers.

**2. Lifecycle rule** (bucket → Management → Create lifecycle rule), so old
versions don't pile up:

- Scope: prefix `results/`.
- Tick **Permanently delete noncurrent versions**: 7 days, keep **10** newer
  versions.
- Tick **Delete expired object delete markers or incomplete multipart
  uploads**: incomplete uploads after 7 days.
- Do **not** tick "Expire current versions": that deletes the live file.

**3. Permissions policy** (IAM → Policies → Create, JSON): read and write one
file, nothing else.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadWriteResultsFile",
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:PutObject"],
      "Resource": "arn:aws:s3:::<bucket>/results/results.duckdb.gz"
    }
  ]
}
```

**4. Role** (IAM → Roles → Create role → Custom trust policy). A role has
two policies: the **trust policy** says who may use it, the **permissions
policy** (step 3, attached on the next screen) says what it can do. To test
locally first, trust your own account; switch to GitHub Actions in Part 3.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "LocalTestingRemoveBeforeCI",
      "Effect": "Allow",
      "Principal": { "AWS": "arn:aws:iam::<account-id>:root" },
      "Action": "sts:AssumeRole"
    }
  ]
}
```

Name it after what it does, e.g. `honest-agent-results-writer`.

**5. Test locally with that role.** Add a profile to `~/.aws/config` (not
`~/.aws/credentials`):

```ini
[profile honest-agent-results-writer]
role_arn = arn:aws:iam::<account-id>:role/honest-agent-results-writer
source_profile = default
```

```bash
export AWS_PROFILE=honest-agent-results-writer
aws sts get-caller-identity       # shows assumed-role/honest-agent-results-writer
aws s3 ls s3://<bucket>/          # must be DENIED: the role can't list
```

**6. First upload, by hand.** Compress the file: a DuckDB file is mostly
reserved space and JSON, and gzip shrinks it 25-100×.

```bash
RESULTS_S3=s3://<bucket>/results/results.duckdb.gz
RESULTS_FILE=honest_agent_results/results.duckdb
honest-agent run
gzip -c "$RESULTS_FILE" | aws s3 cp - "$RESULTS_S3"
```

Create the first file by hand rather than letting the job "create it if
missing": the role can't list the bucket, so a missing file and a permission
error look the same (403). A job that treats any failed download as "first
run" would overwrite your whole history with one run.

**7. Each run:**

```bash
aws s3 cp "$RESULTS_S3" "$RESULTS_FILE.gz" && gunzip -t "$RESULTS_FILE.gz" && gunzip -f "$RESULTS_FILE.gz"
honest-agent run
gzip -c "$RESULTS_FILE" | aws s3 cp - "$RESULTS_S3"
```

The download only replaces the local file once the archive is complete.
Only one job may run this cycle at a time; two overlapping jobs each upload
their own copy and the later one silently drops the other's runs (see Part
3).

## Part 2: hosting the report

### Cloudflare Pages + Cloudflare Access

Free for up to 50 people, with sign-in by email code or SSO (Google, GitHub,
Entra, Okta, any SAML/OIDC provider).

**Set up the sign-in before the first deploy.** A Pages site is public at
`https://<project>.pages.dev` from its first deploy until Access protects it.

**1. Create the project** (needs Node; `npx` fetches wrangler):

```bash
npx wrangler login
npx wrangler pages project create honest-agent-report --production-branch main
```

This reserves `honest-agent-report.pages.dev` without deploying anything.
"Branch" is only a label for direct uploads; always deploy with
`--branch main`, or wrangler guesses it from git.

**2. Turn on Zero Trust** (dashboard → Zero Trust, shown as "Cloudflare
One"): pick the **Free** plan and a team name. The team name appears in the
sign-in address (`<team>.cloudflareaccess.com`).

**3. Make sure email codes are a login method:** Integrations → Identity
providers → add **One-time PIN** if it isn't listed. It may not be on by
default; without it, only people with a Cloudflare account can sign in.

**4. Create the Access application:** Access controls → Applications → Add
an application → **Self-hosted and private**.

- **Destinations → Add public hostname**, twice, picking
  `honest-agent-report.pages.dev` from the Domain dropdown:
  - Subdomain **empty**: the site itself.
  - Subdomain `*`: preview deployments.
- Don't use the **Workers** destination: Pages projects aren't listed there,
  and the Workers it lists are other sites.
- Make sure no row uses one of your own domains: that would put a sign-in in
  front of that whole site.
- Leave "browser-based RDP, SSH, or VNC" off.
- **Policy:** Action Allow, Include → Emails → the people who may view it
  (or an email domain, a GitHub organisation, an identity-provider group).
- **Authentication:** "Accept all available identity providers" is fine.

**5. Check the protection before deploying anything real:**

```bash
curl -s -o /dev/null -w "%{http_code} %{redirect_url}\n" https://honest-agent-report.pages.dev/data/report.json
```

It must answer `302` to `https://<team>.cloudflareaccess.com/...`. Any `200`
means the site is public: stop and fix Access first.

**6. Deploy:**

```bash
honest-agent report
rsync -a --exclude '.*' honest_agent_report/ site/      # leave out honest-agent's hidden helper files
npx wrangler pages deploy site --project-name honest-agent-report --branch main
```

Open the address in a private window: you should get the sign-in page, then
the report.

Caching needs nothing extra: Pages serves every file with
`public, max-age=0, must-revalidate`, so a new deploy shows up on a normal
reload.

### S3 + CloudFront with sign-in at the edge

A private report bucket behind CloudFront, with a Cognito sign-in checked at
CloudFront's edge. AWS publishes the whole setup as one template,
[`cloudfront-authorization-at-edge`](https://github.com/aws-samples/cloudfront-authorization-at-edge):
it creates the report bucket (separate from the results bucket), the
CloudFront distribution, a Cognito user pool and small Lambda@Edge functions
that check every request. Cognito can be connected to your identity provider.

> **Know what you're deploying.** It's an AWS sample, not a supported
> product. Its last published version (2.3.2, September 2024) runs on
> Node.js 20, which no longer gets security patches; the repository's `main`
> branch has moved on but isn't released. For production, consider deploying
> a pinned commit of `main` with the SAM CLI. The template also shows the
> Cognito client secret as a plain stack output: limit who in your AWS
> account can read CloudFormation stacks.

**1. Deploy the template.** Pick your region; the template adds the
Lambda@Edge functions in us-east-1 itself, as AWS requires. With the AWS CLI:

```bash
aws serverlessrepo create-cloud-formation-change-set --region <region> \
  --application-id arn:aws:serverlessrepo:us-east-1:520945424137:applications/cloudfront-authorization-at-edge \
  --semantic-version 2.3.2 --stack-name honest-agent-report-auth \
  --capabilities CAPABILITY_IAM CAPABILITY_RESOURCE_POLICY \
  --parameter-overrides file://params.json
# review the change set (all "Add"), then run it:
aws cloudformation execute-change-set --region <region> \
  --stack-name serverlessrepo-honest-agent-report-auth --change-set-name <name>
```

Parameters (`params.json`, a list of `{"Name": ..., "Value": ...}`):

- `EnableSPAMode` = `false`: login cookies are HTTP-only and Cognito uses a
  client secret. The report doesn't need JavaScript access to the tokens.
- `RewritePathWithTrailingSlashToIndex` = `true`: `/evals/` serves
  `/evals/index.html`.
- `EmailAddress` = the first person's email: Cognito emails them a temporary
  password. Only an admin can add users; nobody can sign up themselves.
- `HttpHeaders`: the template's default content security policy blocks the
  report's fonts and icons (loaded from Google Fonts and unpkg until the
  report bundles them). Pass your own, with
  `font-src https://fonts.gstatic.com` and `img-src 'self' data: https://unpkg.com`.

It takes about 10 minutes; check the stack reaches `CREATE_COMPLETE`. Its
outputs give the address (`WebsiteUrl`) and the bucket (`S3Bucket`).

**2. Check the protection before uploading anything:**

```bash
curl -s -o /dev/null -w "%{http_code} %{redirect_url}\n" https://<id>.cloudfront.net/data/report.json
```

It must answer `307` to your `*.amazoncognito.com` sign-in. The bucket must
refuse direct access (`403`).

**3. Upload the report:**

```bash
REPORT_BUCKET=s3://<bucket from the stack outputs>
aws s3 sync honest_agent_report/ "$REPORT_BUCKET"/ --delete --exclude ".*" --exclude "index.html" --exclude "data/*"
aws s3 cp honest_agent_report/index.html "$REPORT_BUCKET"/index.html --cache-control no-cache
aws s3 cp honest_agent_report/data/ "$REPORT_BUCKET"/data/ --recursive --cache-control no-cache
```

`--delete` removes the template's sample page and old report files;
`--exclude ".*"` keeps honest-agent's hidden helper files out. `no-cache` on
the page and the data makes CloudFront fetch them fresh on every load, so a
new report shows up immediately. The hashed files in `assets/` can be cached.

Check which bucket a `sync --delete` points at before running it: run against
the results bucket with an admin login, it would delete your results.

**4. Adding and removing people.** Users live in the stack's Cognito user
pool, and only an admin can add them: Cognito → User pools → Users → Create
user (email invitation, email marked verified, generated password), or:

```bash
aws cognito-idp admin-create-user --region <region> --user-pool-id <pool id> \
  --username person@example.com \
  --user-attributes Name=email,Value=person@example.com Name=email_verified,Value=true \
  --desired-delivery-mediums EMAIL
```

To remove someone, sign them out everywhere first, then disable them:
disabling alone leaves open sessions refreshable for up to 30 days.

```bash
aws cognito-idp admin-user-global-sign-out --region <region> --user-pool-id <pool id> --username person@example.com
aws cognito-idp admin-disable-user --region <region> --user-pool-id <pool id> --username person@example.com
```

For a company, connect Cognito to your identity provider (Google Workspace,
Entra ID, Okta, SAML/OIDC) so access follows your directory. Then limit it:
assign the app to specific people or groups in the provider, or use the
template's `UserPoolGroupName` so only one Cognito group gets in. Otherwise
everyone in the directory can sign in.

**Removing it:** delete the stack. Deleting the Lambda@Edge part can fail for
a few hours while CloudFront clears its copies; retry later.

## Part 3: running it in CI

Tested with GitHub Actions on 2026-10-08 (four runs): results as a gzipped file in S3,
report on Cloudflare Pages, Slack alerts. Started by hand
(`workflow_dispatch`); a schedule is not tested yet.

Use a **private** repository: workflow logs show agent answers and errors.

### 1. AWS: let GitHub Actions assume the results role

**Create the identity provider first**: IAM → Identity providers → Add
provider → OpenID Connect, URL `https://token.actions.githubusercontent.com`,
audience `sts.amazonaws.com`. IAM may reject a trust policy that names a
provider that doesn't exist yet. An account has only one per URL; reuse it if
it's there.

**Find your repository's subject prefix.** GitHub sends one of two formats,
and the trust policy must match it exactly:

```bash
gh api repos/<owner>/<repo>/actions/oidc/customization/sub    # field sub_claim_prefix
```

- classic: `repo:<owner>/<repo>`
- immutable: `repo:<owner>@<owner_id>/<repo>@<repo_id>`. Safer: a deleted
  repository recreated under the same name can't assume the role.

A mismatch fails with `Not authorized to perform sts:AssumeRoleWithWebIdentity`.
CloudTrail's `AssumeRoleWithWebIdentity` events show the subject GitHub
actually sent.

**Edit the role's trust policy**: IAM → Roles → *your role* → **Trust
relationships** → Edit trust policy. Not the permissions policy: a
`Principal` there is rejected ("Unsupported Principal"). Replace the
local-testing statement with:

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

The permissions policy stays as in Part 1 (read and write the one results
file).

**Check the bucket's region**: names are global, but each bucket lives in
one region, and `AWS_REGION` must be that one:
`aws s3api head-bucket --bucket <bucket>` (`BucketRegion`).

### 2. Cloudflare: a deploy token

My Profile → API Tokens → Create Token → Custom: permission **Account →
Cloudflare Pages → Edit**, limited to your account. Check that Access covers
the preview addresses (`<hash>.<project>.pages.dev`, `main.<project>.pages.dev`),
not only the main one: every CI deploy creates a preview address.

### 3. GitHub: variables and secrets

Variables are not secret (`gh variable set NAME -R <owner>/<repo> --body <value>`):

| Name | Value |
|---|---|
| `AWS_REGION` | the bucket's region |
| `AWS_ROLE_ARN` | `arn:aws:iam::<account-id>:role/<role>` |
| `RESULTS_S3` | `s3://<bucket>/results/results.duckdb.gz` |
| `HONEST_AGENT_REPORT_URL` | `https://<project>.pages.dev/` |
| `CLOUDFLARE_ACCOUNT_ID` | your Cloudflare account ID (`.wrangler/cache/wrangler-account.json` after a local deploy) |

Secrets: `gh secret set NAME -R <owner>/<repo>` prompts without echoing.
Never use `--body` for secrets (it stays in shell history). The prompt needs a
real terminal; without one:
`grep "^NAME=" .env | cut -d= -f2- | gh secret set NAME -R <owner>/<repo>`.

| Name | What |
|---|---|
| `ANTHROPIC_API_KEY` | the model key (or `OPENAI_API_KEY`) |
| the target's token | the variable named by the target's `bearer_token_env`, e.g. `MOTHERDUCK_TOKEN`; read-only. Add any `mcp_env` variables too |
| `CLOUDFLARE_API_TOKEN` | the deploy token |
| `SLACK_WEBHOOK_URL` | the Slack incoming webhook |

### 4. The workflow

Seed the results file once by hand first (Part 1, step 6): the workflow
refuses to run without it, on purpose.

`.github/workflows/honest-agent.yml`; fill in everything marked `<...>`:

```yaml
name: honest-agent

on:
  workflow_dispatch:

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
      CLOUDFLARE_PAGES_PROJECT: <pages-project>
    steps:
      - uses: actions/checkout@v4

      - uses: astral-sh/setup-uv@v6

      - name: Install honest-agent
        run: uv tool install "git+https://github.com/jlcoto/the_honest_agent#subdirectory=cli"

      - uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ vars.AWS_ROLE_ARN }}
          aws-region: ${{ vars.AWS_REGION }}

      - name: Check AWS identity
        run: aws sts get-caller-identity

      # No `|| true`: a failed download must stop the job before anything is overwritten.
      - name: Download results
        id: download
        run: |
          mkdir -p honest_agent_results
          aws s3 cp "$RESULTS_S3" results.duckdb.gz
          gunzip -t results.duckdb.gz
          gunzip -c results.duckdb.gz > honest_agent_results/results.duckdb

      # Exits 0 even when evals fail: the alert comes from `notify`.
      - name: Run evals
        run: honest-agent run --target "$HONEST_AGENT_TARGET"
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          <TARGET_TOKEN_ENV>: ${{ secrets.<TARGET_TOKEN_ENV> }}

      # Save results even if a later step fails, but never when the download failed.
      - name: Upload results
        if: always() && steps.download.outcome == 'success'
        run: gzip -c honest_agent_results/results.duckdb | aws s3 cp - "$RESULTS_S3"

      - name: Build report
        run: honest-agent report

      # Publish a copy without honest-agent's hidden helper files.
      - name: Deploy report
        run: |
          rsync -a --exclude '.*' honest_agent_report/ site/
          npx --yes wrangler pages deploy site --project-name "$CLOUDFLARE_PAGES_PROJECT" --branch main
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ vars.CLOUDFLARE_ACCOUNT_ID }}

      - name: Notify Slack
        run: honest-agent notify --target "$HONEST_AGENT_TARGET"
        env:
          SLACK_WEBHOOK_URL: ${{ secrets.SLACK_WEBHOOK_URL }}
          HONEST_AGENT_REPORT_URL: ${{ vars.HONEST_AGENT_REPORT_URL }}
```

This exact structure ran successfully (target `motherduck`, project
`honest-agent-report`); replace the `<TARGET_TOKEN_ENV>` line with your
target's real variable name. GitHub warns that these action versions run on
Node 20; pin newer major versions when available.

Run it with `gh workflow run honest-agent.yml -R <owner>/<repo>`; follow it
with `gh run watch <run-id> -R <owner>/<repo>` (the run ID is required when
not interactive).

Add `.env`, `*.duckdb`, `*.duckdb.gz`, `honest_agent_results/`,
`honest_agent_report/`, `site/`, `.venv/` and `.wrangler/` to `.gitignore`.

What the test showed: each run appends to the history (6 results became 10
after a second run, no duplicates); the deploy uploads exactly the 6 report
files; Access returned a sign-in redirect for the main, branch and
per-deploy addresses; Slack posted only when an eval fell below threshold.

### Variant: report on S3 + CloudFront

Tested on 2026-10-08 (one run, all steps passed), with the CloudFront stack
from Part 2. Same results handling, same role, same trust policy; the report
goes to the stack's bucket instead of Cloudflare, then CloudFront's cache is
cleared. Both workflows can live in one repository: they share the
`concurrency` group, so they never write the results file at the same time.

**Read the stack's outputs by name.** `describe-stacks` prints every output,
including the Cognito client secret (and grepping for "secret" misses it:
name and value can be on different lines). Ask only for what you need, in
the region you deployed the stack to:

```bash
aws cloudformation describe-stacks --region <region> --stack-name serverlessrepo-honest-agent-report-auth \
  --query "Stacks[0].Outputs[?OutputKey=='S3Bucket'||OutputKey=='CloudFrontDistribution'||OutputKey=='WebsiteUrl']"
```

The secret is built into the edge functions, so changing it means
redeploying the stack.

**Extra permissions for the role**: IAM → Roles → *your role* →
**Permissions** → Add permissions → Create inline policy → JSON. The trust
policy doesn't change.

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

`s3 sync` needs the listing, `--delete` the delete. Because of `--delete`,
the bucket must hold nothing but the report; the stack's bucket doesn't. Its
encryption (SSE-S3) needs no KMS permissions; a bucket of your own with
SSE-KMS would also need `kms:GenerateDataKey` on its key.

**Variables** on top of Part 3's: `REPORT_S3_BUCKET` (output `S3Bucket`,
without `s3://`), `REPORT_S3_REGION` (the stack's region; it can differ from
the results bucket's `AWS_REGION`), `CLOUDFRONT_DISTRIBUTION_ID` (output
`CloudFrontDistribution`), and `HONEST_AGENT_REPORT_URL` = output
`WebsiteUrl` plus `/`. No Cloudflare secrets.

**Workflow** `.github/workflows/honest-agent-s3.yml`: the same as above up to
**Build report**; replace the last three steps and add the variables to the
job's `env:`:

```yaml
    env:
      RESULTS_S3: ${{ vars.RESULTS_S3 }}
      HONEST_AGENT_TARGET: <target>
      REPORT_S3_BUCKET: ${{ vars.REPORT_S3_BUCKET }}
      REPORT_S3_REGION: ${{ vars.REPORT_S3_REGION }}
      CLOUDFRONT_DISTRIBUTION_ID: ${{ vars.CLOUDFRONT_DISTRIBUTION_ID }}
    steps:
      # ... checkout, install, AWS login, download, run, upload, build report as above ...

      # A copy without hidden files; --delete removes old hashed assets.
      - name: Deploy report to S3
        run: |
          rsync -a --exclude '.*' honest_agent_report/ site/
          aws s3 sync site/ "s3://$REPORT_S3_BUCKET/" --delete --region "$REPORT_S3_REGION"

      # Drop CloudFront's cached copy so the new report is served right away.
      - name: Invalidate CloudFront
        run: aws cloudfront create-invalidation --distribution-id "$CLOUDFRONT_DISTRIBUTION_ID" --paths '/*' --query 'Invalidation.{id:Id,status:Status}' --output text

      - name: Notify Slack
        run: honest-agent notify --target "$HONEST_AGENT_TARGET"
        env:
          SLACK_WEBHOOK_URL: ${{ secrets.SLACK_WEBHOOK_URL }}
          HONEST_AGENT_REPORT_URL: ${{ vars.HONEST_AGENT_REPORT_URL }}
```

`/*` counts as one path toward CloudFront's 1,000 free invalidation paths a
month.

**Recommended addition** (each part tested, the combination not yet in CI):
the invalidation refreshes CloudFront, but without a cache header browsers
may keep an old `index.html` or `report.json` for a while. Upload those two
with `no-cache`, as in Part 2:

```bash
aws s3 sync site/ "s3://$REPORT_S3_BUCKET/" --delete --region "$REPORT_S3_REGION" --exclude "index.html" --exclude "data/*"
aws s3 cp site/index.html "s3://$REPORT_S3_BUCKET/index.html" --cache-control no-cache --region "$REPORT_S3_REGION"
aws s3 cp site/data/ "s3://$REPORT_S3_BUCKET/data/" --recursive --cache-control no-cache --region "$REPORT_S3_REGION"
```

With these, CloudFront also checks for a new version on every load, so the
invalidation becomes optional.

**After the first run, check:** `curl -sI https://<id>.cloudfront.net/`
answers 307 to `*.amazoncognito.com`; a direct S3 object URL answers 403;
signing in shows the new run.

## Known issues

- **Slack links lose the result after signing in.** An alert links to
  `<report>#/result/<id>`; behind any sign-in, the part after `#` is dropped
  during the login redirect, so people land on the Overview. A fix is
  planned (`?result=<id>` links).
- **Hidden helper files.** The report folder holds `.gitignore` and
  `.honest_agent_report`; `wrangler pages deploy` would publish them, hence
  the `rsync --exclude '.*'` copy above. A fix in honest-agent is planned.
