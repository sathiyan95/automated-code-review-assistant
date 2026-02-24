# Deployment Instructions

Your Automated Code Review Assistant has been fully migrated to a production-grade AWS serverless CI/CD architecture.

## Architecture Overhaul Status

- 🟢 **Frontend**: Static Web Hosting on AWS S3 (`frontend/` contents). Dynamic variables and reports polling via AWS API Gateway and S3 bucket fetching.
- 🟢 **Backend / HTTP Layer**: AWS API Gateway routes traffic to our new `AnalyzeControllerLambda`. **No EC2 or manual servers required.**
- 🟢 **Controllers & Workers**: `AnalyzeControllerLambda` receives the GitHub HTTP requests, checks repo, stores commit stubs to S3, then asynchronously executes `GenAICodeReviewer` and `TechDebtAnalyzerJob`.
- 🟢 **GenAICodeReviewer (Lambda)**: Stateless, runs in Python 3.11 up to 120s, leverages `GENAI_API_KEY` environment variable. Generates structured JSON data directly into the Reports S3 bucket.
- 🟢 **TechDebtAnalyzer (Glue job)**: Uses Apache Spark framework configured for Python shell to analyze large commit logs securely.
- 🟢 **CI/CD Integration**: AWS CodePipeline watches this config repo. CodeBuild deploys the frontend variables (using exact API URL) and injects updated Lambda Zip code blocks natively.
- 🟢 **Security**: All hardcoded identifiers/keys removed. Everything goes via Secure String Parameters -> Environment Variables.

## Deployment Steps

1. **Commit your code to GitHub.**
   Ensure your changes (`cloudformation.yaml`, `buildspec.yml`, `backend/`, `frontend/`) are pushed to the `main` branch of your AWS pipeline-linked repository.

2. **Generate GitHub Token & Settings:**
   - Create a Fine-Grained Personal Access Token in GitHub (Needs `repo` and `webhook` hooks access).
   - Get your Gemini AI API Token.

3. **Deploy using CloudFormation (First time only):**
   Go to AWS Console -> CloudFormation -> Create Stack.
   Upload `infrastructure/cloudformation.yaml`.
   Fill in the parameters:
   - `GitHubRepoOwner`: Your GitHub account username.
   - `GitHubRepoName`: The repository where this assistant is housed.
   - `GitHubBranch`: `main`
   - `GitHubToken`: Your generated Fine-Grained Token.
   - `GenAIApiKey`: Your Google Gemini API Key.

   Acknowledge IAM creation and **Deploy**.

4. **Verify Deployment**:
   - CloudFormation returns the `WebsiteUrl`, `ApiEndpoint`, and `ReportsBucketName` in the Outputs tab.
   - The initial deployment builds CodePipeline, which automatically triggers CodeBuild.
   - CodeBuild will parse `buildspec.yml`, construct lambdas securely, seed S3 frontend, edit endpoints in JavaScript seamlessly, and kickstart operations.

5. **Interact:**
   Click the output `WebsiteUrl` (e.g., `http://your-bucket.s3-website-region.amazonaws.com`).
   Type any public GitHub URL (e.g., `https://github.com/pallets/flask`) into the UI and analyze. No backend manual commands required.

**Clean-up Notes**:

- Reverted all localhost logic.
- Removed arbitrary mock demo responses from Lambdas; Lambdas will intelligently degrade if they hit Google AI rate limits, but standard structure json relies entirely on S3 status polling.
- `main.py` (FastAPI Server) removed.
