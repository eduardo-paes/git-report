# GitHub Contribution Report Generator

Generate a comprehensive report of your contributions to any GitHub repository.

## Features

- 📊 Detailed contribution statistics (commits, PRs, reviews, issues)
- 📈 Monthly activity heatmap
- 📱 Social media ready HTML output

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

### 4. Install Dependencies

Generate a virtual environment and install dependencies:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 5. Run the Report

```bash
python github_contributions.py
```