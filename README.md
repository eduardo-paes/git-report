# GitHub Contribution Report Generator

Generate a comprehensive report of your contributions to any GitHub repository.

## Features

- 📊 Detailed contribution statistics (commits, PRs, reviews, issues)
- 📈 Monthly activity heatmap
- 📱 Social media ready text output

## Quick Start

### 1. Clone or Download Files

Make sure you have these files in your project directory:

```txt
github_contributions.py
.env.example
requirements.txt
```

### 2. Configure Your Settings

Edit the `.env` file with your details. Fill in:

- `GITHUB_TOKEN`: Your GitHub personal access token
- `GITHUB_USERNAME`: Your GitHub username
- `GITHUB_ORG`: The organization name
- `GITHUB_REPO`: The repository name
- `YEAR`: Year to analyze (optional)

### 3. Get Your GitHub Token

1. Go to https://github.com/settings/tokens
2. Click "Generate new token (classic)"
3. Give it a descriptive name
4. Select scopes: ✅ `repo` and ✅ `read:user`
5. Click "Generate token"
6. Copy the token (you won't see it again!)
7. Paste it in your `.env` file

### 4. Run the Report

```bash
source venv/bin/activate
python github_contributions.py
```

## Manual Setup

If you prefer to set up manually:

```bash
# Create virtual environment
python3 -m venv venv

# Activate it
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run the script
python github_contributions.py
```

## Output Example

The script generates:

### Console Report

```bash
💻 COMMITS
  Total Commits: 156
  Files Changed: 423
  Lines Added: +12,456
  Lines Deleted: -3,234
  Net Change: +9,222 lines

🔀 PULL REQUESTS
  Total PRs: 45
  Merged: 42 ✅
  Closed: 2
  Open: 1
  Merge Rate: 93.3%
```

### Social Media Post

```bash
🎯 My 2024 Contributions to microsoft/vscode

💻 156 commits
📝 12,456+ / 3,234- lines of code
🔀 42 PRs merged
👀 28 PRs reviewed
🐛 15 issues created

Total impact: 246 contributions! 🚀
```
