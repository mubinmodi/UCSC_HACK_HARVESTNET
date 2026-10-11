# Deploying the API skeleton to AWS Lambda

Ticket #1. This puts the example-data API at a public HTTPS address (a Lambda Function URL), so the frontend can call it from a browser. It returns only the agreed example responses (`docs/contracts/examples/public-api/`). It stores nothing and decides nothing. Nothing here has been deployed yet.

## 1. Build the zip

From the repo root:

```sh
cd api_skeleton && uv run python -m harvestnet_api_skeleton.build_lambda
```

It writes `api_skeleton/dist/harvestnet-api-skeleton-lambda.zip` and needs no packages beyond the standard library. The zip holds:

```
harvestnet_api_skeleton/__init__.py
harvestnet_api_skeleton/routes.py            # route table and example lookup
harvestnet_api_skeleton/lambda_function.py   # lambda_handler
harvestnet_api_skeleton/server.py            # local server (unused on Lambda)
harvestnet_api_skeleton/examples/public-api/*.json   # one example per operation
```

Rebuild and re-upload whenever an example changes.

## 2. Create the function

| Setting | Value |
|---|---|
| Runtime | `python3.12` |
| Architecture | `arm64` (`x86_64` also works) |
| Handler | `harvestnet_api_skeleton.lambda_function.lambda_handler` |
| Code | the zip from step 1 |
| Memory / timeout | 128 MB / 10 seconds |
| Execution role | a new role with only `AWSLambdaBasicExecutionRole` (CloudWatch logs) |
| Environment | `HARVESTNET_CORS=url` (see step 3) |

## 3. Add the Function URL

| Setting | Value |
|---|---|
| Auth type | `NONE` (public; the skeleton serves only synthetic example data) |
| CORS: allow origins | `*` |
| CORS: allow methods | `GET`, `POST`, `PUT` |
| CORS: allow headers | `content-type`, `authorization` |
| CORS: max age | `600` |

**Pick one place for CORS headers.** With CORS configured on the Function URL, Lambda adds the headers itself. If the function also sent them, GET and POST responses would carry `Access-Control-Allow-Origin` twice, and browsers reject that. So set `HARVESTNET_CORS=url` on the function, as in step 2. (Without that variable, the function adds the headers itself, which is right only if the Function URL has no CORS settings.)

In the console, creating a URL with auth type `NONE` also adds the public-access policy. With the CLI, add it yourself:

```sh
aws lambda create-function-url-config --function-name harvestnet-api-skeleton --auth-type NONE \
  --cors '{"AllowOrigins": ["*"], "AllowMethods": ["GET", "POST", "PUT"], "AllowHeaders": ["content-type", "authorization"], "MaxAge": 600}'
aws lambda add-permission --function-name harvestnet-api-skeleton --statement-id FunctionURLAllowPublicAccess \
  --action lambda:InvokeFunctionUrl --principal '*' --function-url-auth-type NONE
aws lambda add-permission --function-name harvestnet-api-skeleton --statement-id FunctionURLAllowInvokeAction \
  --action lambda:InvokeFunction --principal '*' --invoked-via-function-url
```

## 4. Check it

```sh
curl -s https://YOUR-URL-ID.lambda-url.YOUR-REGION.on.aws/health
curl -s https://YOUR-URL-ID.lambda-url.YOUR-REGION.on.aws/       # lists every operation
```

Then add the address to "How to call it" in `docs/contracts/public-api.md`, and ask the frontend person to call it from a browser page (the last box on ticket #1).

## Notes

- Locally, `uv run python -m harvestnet_api_skeleton.server` serves the same routes at `http://127.0.0.1:8040`.
- Anyone with the URL can call it. That's acceptable only while it serves synthetic examples. Before real logic (Lane A, #9) goes behind it, add staff sign-in and household tokens (contracts README, decision 12), and revisit auth type `NONE`.
- Request paths can hold request codes, so the function logs nothing about requests.
