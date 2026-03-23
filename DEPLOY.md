# Deploying GlucoTrack AI to Google Cloud Run (PowerShell Guide)

This guide explains how to deploy the GlucoTrack AI bot to Google Cloud Run using **PowerShell**.

## 1. Environment Setup

Ensure your local `.env` variables are ready. The deployment will ignore your local `.env` file and use Secret Manager instead.

## 2. Secrets Management

Store all sensitive information in **Google Secret Manager**.

### Step 2a: Create the Secrets
Run these commands in PowerShell to create the secret containers:
```powershell
gcloud secrets create oracle-glucotrack-wallet-zip --replication-policy="automatic"
gcloud secrets create db-user --replication-policy="automatic"
gcloud secrets create db-password --replication-policy="automatic"
gcloud secrets create db-dsn --replication-policy="automatic"
gcloud secrets create wallet-password --replication-policy="automatic"
gcloud secrets create telegram-bot-token --replication-policy="automatic"
```

### Step 2b: Add the Values (Versions)
Use `Write-Output -NoEnumerate` with `-NoNewline` to pipe values without trailing newlines:
```powershell
# For the Wallet ZIP file
gcloud secrets versions add oracle-glucotrack-wallet-zip --data-file=".\Wallet_GlucoTrack.zip"

# For text-based secrets
Write-Output -NoNewline "YOUR_DB_USER" | gcloud secrets versions add db-user --data-file=-
Write-Output -NoNewline "YOUR_DB_PASSWORD" | gcloud secrets versions add db-password --data-file=-
Write-Output -NoNewline "YOUR_DB_DSN" | gcloud secrets versions add db-dsn --data-file=-
Write-Output -NoNewline "YOUR_WALLET_PASSWORD" | gcloud secrets versions add wallet-password --data-file=-
Write-Output -NoNewline "YOUR_TELEGRAM_BOT_TOKEN" | gcloud secrets versions add telegram-bot-token --data-file=-
```

## 3. Build and Deploy

In PowerShell, use the backtick (`` ` ``) for line continuation.

### Deployment Command

```powershell
gcloud run deploy glucotrack-bot `
  --source . `
  --region asia-south1 `
  --allow-unauthenticated `
  --port 8080 `
  --set-env-vars="MODE=webhook" `
  --set-env-vars="GOOGLE_CLOUD_PROJECT=[YOUR_PROJECT_ID]" `
  --set-env-vars="GOOGLE_CLOUD_LOCATION=asia-south1" `
  --set-secrets="/secrets/wallet.zip=oracle-glucotrack-wallet-zip:latest" `
  --set-secrets="DB_USER=db-user:latest" `
  --set-secrets="DB_PASSWORD=db-password:latest" `
  --set-secrets="DB_DSN=db-dsn:latest" `
  --set-secrets="WALLET_PASSWORD=wallet-password:latest" `
  --set-secrets="TELEGRAM_BOT_TOKEN=telegram-bot-token:latest"
```

## 4. Post-Deployment: Set Webhook

After deployment, Cloud Run will provide a URL (e.g., `https://glucotrack-bot-xyz-uc.a.run.app`).

```powershell
gcloud run services update glucotrack-bot `
  --region asia-south1 `
  --set-env-vars="WEBHOOK_URL=https://glucotrack-bot-xyz-uc.a.run.app"
```

## 6. Continuous Deployment (CI/CD)

To automatically redeploy every time you push a commit to your GitHub repository, you can link your repository to Cloud Run.

### Step 6a: Connect your Repository
1.  Go to the [Cloud Run Console](https://console.cloud.google.com/run).
2.  Select your service `glucotrack-bot`.
3.  Click **SET UP CONTINUOUS DEPLOYMENT**.
4.  Follow the prompts to authenticate with GitHub and select your repository and branch (`main`).

### Step 6b: Automate with PowerShell
Alternatively, you can set up the build trigger directly from PowerShell:

```powershell
gcloud beta run services set-replication-filter glucotrack-bot --region asia-south1

# This command creates a Cloud Build Trigger linked to your GitHub repo
gcloud alpha builds triggers create github `
    --name="glucotrack-deploy-trigger" `
    --repo-owner="[YOUR_GITHUB_USERNAME]" `
    --repo-name="[YOUR_REPO_NAME]" `
    --branch-pattern="main" `
    --dockerfile="Dockerfile" `
    --region=asia-south1
```

*Note: The first time you do this, Google Cloud will ask you to connect your GitHub account via a browser link.*

### Step 6c: Handling Secrets in CI/CD
When Cloud Build runs, it uses the **Cloud Build Service Account**. You must grant it permission to access your secrets:

```powershell
# Get your Project Number
$PROJECT_NUMBER = gcloud projects list --filter="project_id:[YOUR_PROJECT_ID]" --format="value(projectNumber)"

# Grant Secret Manager Access to the Cloud Build Service Account
gcloud projects add-iam-policy-binding [YOUR_PROJECT_ID] `
    --member="serviceAccount:$PROJECT_NUMBER@cloudbuild.gserviceaccount.com" `
    --role="roles/secretmanager.secretAccessor"
```

Once linked, any `git push` to the `main` branch will automatically:
1.  Build a new Docker image.
2.  Push it to Google Artifact Registry.
3.  Deploy a new revision to Cloud Run with all your pre-configured secrets.

