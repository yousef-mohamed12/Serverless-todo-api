# Serverless To-Do API with Cognito, DynamoDB & WAF

AWS Solutions Architect – Associate graduation project (Project 3). A serverless REST API where each signed-in user manages a private to-do list, served globally through CloudFront and protected by WAF. Everything is defined as code (AWS SAM) and deploys with one command.

![Architecture](docs/architecture.svg)

## How it works

1. The browser loads the static frontend from a **private S3 bucket** through **CloudFront** (Origin Access Control, HTTPS only).
2. The user signs in with the **Cognito hosted UI** (authorization code flow with PKCE) and receives a JWT.
3. The frontend calls `/api/*` on the same CloudFront domain, which forwards to **API Gateway**. **WAF** inspects the request first (rate limit and AWS managed rules).
4. API Gateway's **Cognito authorizer** validates the JWT. Invalid or missing token returns `401` before Lambda runs.
5. **Lambda** reads the user's `sub` claim and runs the CRUD operation on **DynamoDB**, always scoped to that user's partition key. Users cannot read each other's data.
6. Every item change lands on **DynamoDB Streams**, which triggers a second Lambda (a hook for audit/notifications).
7. **X-Ray** traces each request across API Gateway, Lambda and DynamoDB.

## AWS services and why they were chosen

| Service | Role | Design decision |
|---|---|---|
| CloudFront | Single entry point for site and API | One domain means no CORS; edge caching for static assets; `/api/*` uses a no-cache policy and forwards the `Authorization` header |
| S3 | Static frontend | Fully private, public access blocked, only CloudFront can read (OAC) |
| WAF (regional) | Edge-style protection for the API | Rate limit per client IP (via `X-Forwarded-For`, because CloudFront hides the real IP), Common, Known Bad Inputs and IP Reputation managed rule groups |
| API Gateway (REST) | API front door | Cognito authorizer, stage throttling, optional response cache, X-Ray enabled |
| Cognito User Pool | Authentication | Email sign-up, verified email, password policy, hosted UI |
| Lambda | Business logic | One function with least-privilege IAM (`DynamoDBCrudPolicy` on one table only) |
| DynamoDB | Storage | On-demand billing; PK `userId`, SK `todoId` (time-sortable); GSI `status-index` for "open/done" queries; PITR and encryption on; Streams on |
| X-Ray | Tracing | Active tracing on Lambda and API stage; SDK patches boto3 for DynamoDB subsegments |

**Why WAF is regional, not on CloudFront:** CloudFront-scoped WAF must be created in `us-east-1` and complicates a single-template deploy. Attaching it to the API Gateway stage protects the API directly and works in any Region.

## Data model

| Attribute | Type | Notes |
|---|---|---|
| `userId` (PK) | String | Cognito `sub` |
| `todoId` (SK) | String | `<epoch-ms>-<random>`, so newest-first queries need no extra index |
| `title` | String | 1–200 chars |
| `status` | String | `open` or `done` (GSI sort key) |
| `createdAt` | Number | Unix seconds |

Access patterns: list all my todos (query on table), list my todos by status (query on GSI), get/update/delete one (key lookup).

## API

All routes require `Authorization: <Cognito ID token>`.

| Method | Path | Description |
|---|---|---|
| GET | `/api/todos[?status=open\|done]` | List the caller's todos |
| POST | `/api/todos` | Create `{ "title": "..." }` |
| GET | `/api/todos/{id}` | Read one |
| PUT | `/api/todos/{id}` | Update `title` and/or `status` |
| DELETE | `/api/todos/{id}` | Delete (returns `204`) |

## Deploy

**Prerequisites:** an AWS account, [AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html) configured (`aws configure`), [AWS SAM CLI](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html), Python 3.12.

```bash
git clone <your-repo-url> && cd serverless-todo-api
./deploy.sh
```

The script builds, deploys the stack, writes `frontend/config.js` with the Cognito settings, uploads the site to S3, invalidates CloudFront and prints the site URL. Open it, create an account (a verification email is sent) and add tasks.

Use a different Region or stack name with `AWS_REGION=eu-west-1 STACK=my-todo ./deploy.sh` (keep the stack name lowercase).

### Test the API from the terminal

```bash
POOL=<UserPoolId output>; CLIENT=<UserPoolClientId output>; URL=<ApiUrl output>
aws cognito-idp admin-create-user --user-pool-id $POOL --username me@example.com --message-action SUPPRESS
aws cognito-idp admin-set-user-password --user-pool-id $POOL --username me@example.com --password 'Str0ngPassw0rd1' --permanent
TOKEN=$(aws cognito-idp initiate-auth --client-id $CLIENT --auth-flow USER_PASSWORD_AUTH \
  --auth-parameters USERNAME=me@example.com,PASSWORD='Str0ngPassw0rd1' --query AuthenticationResult.IdToken --output text)

curl -s -X POST $URL -H "Authorization: $TOKEN" -d '{"title":"Learn Cognito"}'
curl -s $URL -H "Authorization: $TOKEN"
curl -si $URL        # no token -> 401 Unauthorized
```

### Demonstrate each feature (good for your video)

- **Auth:** call the API without a token (`401`), then with one (`200`).
- **WAF:** send a request with a SQL-injection-style query string and see the block in the WAF sampled requests, or lower `RateLimit` and loop requests with `curl`.
- **Caching:** redeploy with `./deploy.sh --parameter-overrides EnableApiCache=true`, call `GET /api/todos` twice and compare latency/Lambda invocations in CloudWatch. Turn it off afterwards (the cache cluster is billed hourly).
- **X-Ray:** open CloudWatch → X-Ray traces → Service map to see API Gateway → Lambda → DynamoDB.
- **Streams:** create a todo, then check the stream Lambda's CloudWatch log group.

## Cost

Designed to stay in or near the free tier for a demo: Lambda, DynamoDB on-demand, API Gateway, CloudFront and Cognito usage is tiny. The costs that do not scale to zero are **WAF** (about $5/month for the web ACL plus about $1 per rule group, prorated hourly) and the optional **API cache** (about $0.02/hour when enabled). Run `./cleanup.sh` as soon as you have captured your screenshots or video.

## Clean up

```bash
./cleanup.sh
```

Empties the S3 bucket and deletes the stack, removing every resource.

## Security summary (Well-Architected: Security pillar)

- Authentication at the edge of the API (Cognito JWT) and per-user data isolation by key design.
- WAF managed rules plus per-IP rate limiting; API Gateway throttling as a second layer.
- Private S3 bucket (OAC), HTTPS enforced, DynamoDB encryption at rest and point-in-time recovery.
- Least-privilege IAM: the function can only touch one table.
- Note: `ALLOW_USER_PASSWORD_AUTH` is enabled on the app client for CLI testing only. Remove it from `template.yaml` for production.

## Exam mapping (SAA-C03)

Decoupled, serverless design (Domain 2: Resilient), least-privilege and edge protection (Domain 1: Secure), DynamoDB key and GSI design, on-demand capacity and caching (Domain 3/4: Performance and Cost).

## Repository structure

```
├── template.yaml        # SAM/CloudFormation: all infrastructure
├── src/app.py           # Lambda CRUD handler
├── src/requirements.txt # X-Ray SDK
├── frontend/index.html  # Static single-page app (Cognito PKCE login)
├── deploy.sh            # Build, deploy, upload site
├── cleanup.sh           # Tear everything down
└── docs/architecture.svg|png
```

## Possible improvements

Custom domain with Route 53 and ACM, CloudWatch alarms with SNS, a CI/CD pipeline (CodePipeline or GitHub Actions), and separate Lambda functions per route.

## Author

Your name · [LinkedIn](https://linkedin.com) · Add screenshots and your demo video link here.
#Serverless-todo-api
