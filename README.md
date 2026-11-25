# To-Do App on AWS: Simple Guide

A plain-language guide to the Serverless To-Do project. Read this first, then use the README for the technical details.

## What this project is

A small web app where people sign in and keep a private to-do list. The app is simple on purpose. The real goal is to show how AWS services work together to make an app that is secure, fast and needs no servers to manage.

## The parts, in everyday terms

| Part | What it does | Think of it as |
| --- | --- | --- |
| S3 | Stores the website files (the page people see) | A shelf holding the website |
| CloudFront | Delivers the website and API quickly and over HTTPS | The front door everyone enters through |
| WAF | Blocks attacks and too many requests from one person | A security guard at the door |
| Cognito | Handles sign-up, sign-in and gives users a login token | The ID check |
| API Gateway | Receives requests and checks the login token | The reception desk |
| Lambda (CRUD) | Runs the code that adds, reads, updates and deletes tasks | The worker |
| DynamoDB | Stores the tasks | The filing cabinet |
| DynamoDB Streams + Lambda (stream) | Reacts whenever a task changes | A bell that rings when a file changes |
| X-Ray | Shows how long each step took | A tracker following each request |

## What happens when a user adds a task

1. The user opens the site. CloudFront serves the page from S3.
2. The user clicks Sign in. Cognito checks their account and gives the browser a login token.
3. The user types a task and clicks Add. The browser sends the request with the token.
4. WAF checks the request is not an attack and not too frequent.
5. API Gateway checks the token with Cognito. No valid token means the request stops with a 401 error.
6. Lambda reads who the user is from the token and saves the task in DynamoDB under that user.
7. DynamoDB Streams notices the new item and triggers the second Lambda, which writes a log line.
8. X-Ray records the whole journey so you can see where time was spent.

## Why it is designed this way

- **Serverless:** no servers to patch or scale. You pay only when the app is used.
- **Secure:** only logged-in users reach the data, each user only sees their own tasks, and the S3 bucket is private.
- **Fast:** CloudFront caches the website near users and API Gateway can cache responses.
- **Everything as code:** one template file builds the entire project, and one command deletes it.

## The files in the project

- template.yaml: describes every AWS resource
- src/app.py: the Lambda code (create, read, update, delete)
- frontend/index.html: the web page
- deploy.sh and cleanup.sh: build everything and delete everything
- docs/: the architecture diagram
- README.md: full technical documentation

## Explain it in one minute

This is a serverless to-do app on AWS. Users load the site from S3 through CloudFront and sign in with Cognito. Every API request passes through WAF, then API Gateway, which checks the Cognito token. A Lambda function handles the create, read, update and delete actions and stores each user's tasks in DynamoDB. Changes in DynamoDB trigger a second Lambda through Streams, and X-Ray traces the request from API Gateway to DynamoDB. It is secure, scalable and has no servers to manage.

## 
