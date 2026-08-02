# ArXiv Paper Summarizer

A GitHub Actions workflow that fetches recent ArXiv papers, filters them using LLMs, summarizes them, and publishes the results as GitHub Issues.

## Features
- **Smart Filtering**: Uses `gpt-5-mini` to score paper relevance (0-10) based on your keywords.
- **Concise Summaries**: Generates high-quality summaries using `gpt-5`.
- **Flexible LLM Support**: Uses Microsoft Foundry/Azure OpenAI by default and supports other OpenAI-compatible APIs.
- **Incremental Fetching**: Only fetches papers published since the last run to avoid duplicates.
- **Daily Schedule**: Runs automatically every day at 07:00 UTC.
- **Reading List**: Mark papers to read later with a checkbox, automatically tracked in a dedicated issue.

## Configuration

Edit `config.yaml` to customize your preferences:

```yaml
arxiv:
  categories:
    - "cs.AI"
    - "cs.LG"
  keywords:
    - "LLM"
    - "Agent"
  max_results: 20

github:
  usernames:
    - "your-username" # Users to tag in the issue
  issue_label: "arxiv-summary"
  max_papers_per_issue: 10 # Split into multiple issues when more papers are found

llm_service:
  # Set this here or with LLM_BASE_URL:
  base_url: "https://<resource>.openai.azure.com/openai/v1/"

models:
  # Azure deployment names
  filter: "gpt-5-mini"
  summarize: "gpt-5"
```

### Microsoft Foundry / Azure OpenAI

This repository consumes pre-existing Azure resources; it does not provision them.

1. Create a Microsoft Foundry or Azure OpenAI resource.
2. Deploy `gpt-5-mini` for filtering and `gpt-5` for summarization. If you choose different deployment names, update the `models` values in `config.yaml`.
3. Copy the resource's OpenAI-compatible v1 endpoint and API key.

Supported endpoint formats include:

```yaml
llm_service:
  base_url: "https://<resource>.openai.azure.com/openai/v1/"

# A Microsoft Foundry resource endpoint can also be used:
llm_service:
  base_url: "https://<resource>.services.ai.azure.com/openai/v1/"
```

Model availability and quota vary by Azure region.

### Using Other LLM Providers

The tool retains support for OpenAI-compatible APIs. Configure `llm_service` in `config.yaml` or set `LLM_BASE_URL`:

```yaml
# OpenAI
llm_service:
  base_url: "https://api.openai.com/v1"

# Local
llm_service:
  base_url: "http://localhost:11434/v1"
```

Set the provider configuration through environment variables:
- `LLM_BASE_URL` - Overrides the base URL in `config.yaml`.
- `LLM_API_KEY` - The provider API key.

## GitHub Actions

### ArXiv Summarizer

The workflow is defined in `.github/workflows/summarize.yml`. It is configured to run:
- **Daily** at 07:00 UTC.
- **Manually** via the "Run workflow" button in the Actions tab.

#### Configuring Microsoft Foundry in GitHub Actions

Add these repository secrets before running the workflow:

1. `LLM_BASE_URL` - The Azure OpenAI-compatible v1 endpoint.
2. `LLM_API_KEY` - The Azure resource API key.

The workflow's `GITHUB_TOKEN` is used only to read and create GitHub Issues.

### Reading List

Each paper summary includes a "📚 Read Later" checkbox. When you check this box:

1. A GitHub workflow detects the change (`.github/workflows/reading-list.yml`)
2. The paper title and ArXiv link are automatically added to a **📚 ArXiv Reading List** issue
3. The reading list issue is created automatically if it doesn't exist (labeled `reading-list`)

This lets you quickly bookmark interesting papers while reviewing the daily digest, with all your selections tracked in one place.

## Local Development & Testing

You can run the tool locally without GitHub Actions.

### Prerequisites
1. Install [uv](https://github.com/astral-sh/uv) (or use pip).
2. A GitHub Personal Access Token (PAT) with issue read/write access.
3. A Microsoft Foundry/Azure OpenAI v1 endpoint, API key, and deployed models.

### Setup
```bash
# Install dependencies
uv sync
```

### Running Locally
1. Create a `.env` file in the root directory:
   ```bash
   GITHUB_TOKEN=your_fine_grained_token
   GITHUB_REPOSITORY=owner/repo
   LLM_BASE_URL=https://your-resource.openai.azure.com/openai/v1/
   LLM_API_KEY=your_azure_api_key
   ```
2. Run the summarizer:
   ```bash
   uv run src/main.py
   ```

**Token Permissions (Fine-grained):**
- **Issues**: `Read and Write` (to create summaries and check last run).

> [!NOTE]
> When running locally, the tool will try to create a real issue in the specified repository. If you just want to test the fetching/summarizing logic without creating an issue, you can modify `src/main.py` or `src/issue_creator.py` temporarily.
