#!/usr/bin/env python3
import requests
from datetime import datetime
from collections import defaultdict
import os
import time
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration from environment
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
USERNAME = os.getenv("GITHUB_USERNAME")
ORGANIZATION = os.getenv("GITHUB_ORG")
REPOSITORY = os.getenv("GITHUB_REPO")
YEAR = int(os.getenv("YEAR", datetime.now().year))

# GitHub API base URL
API_BASE = "https://api.github.com"

headers = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json"
}

def validate_config():
    """Validate that all required configuration is present"""
    required = {
        "GITHUB_TOKEN": GITHUB_TOKEN,
        "GITHUB_USERNAME": USERNAME,
        "GITHUB_ORG": ORGANIZATION,
        "GITHUB_REPO": REPOSITORY
    }
    
    missing = [key for key, value in required.items() if not value]
    
    if missing:
        print("❌ Missing required configuration:")
        for key in missing:
            print(f"   - {key}")
        print("\n📝 Please create a .env file with these variables.")
        print("   See .env.example for reference.")
        return False
    
    return True

def check_rate_limit():
    """Check remaining API rate limit"""
    response = requests.get(f"{API_BASE}/rate_limit", headers=headers)
    if response.status_code == 200:
        data = response.json()
        core = data['resources']['core']
        remaining = core['remaining']
        limit = core['limit']
        reset_time = datetime.fromtimestamp(core['reset'])
        
        if remaining < 100:
            print(f"⚠️  Low API rate limit: {remaining}/{limit} remaining")
            print(f"   Resets at: {reset_time.strftime('%H:%M:%S')}")
        
        return remaining
    return None

def get_date_range(year):
    """Get start and end dates for the year"""
    start_date = datetime(year, 1, 1)
    end_date = datetime(year, 12, 31, 23, 59, 59)
    return start_date, end_date

def fetch_all_pages(url, params=None):
    """Fetch all pages from a paginated API endpoint with rate limit handling"""
    results = []
    page = 1
    
    while True:
        if params is None:
            params = {}
        params['page'] = page
        params['per_page'] = 100
        
        response = requests.get(url, headers=headers, params=params)
        print(f" Fetching page {url} (page {page}) - Status: {response.status_code}")
        
        if response.status_code == 403 and 'rate limit' in response.text.lower():
            reset_time = int(response.headers.get('X-RateLimit-Reset', 0))
            if reset_time:
                wait_time = reset_time - time.time() + 5
                print(f"⏳ Rate limit hit. Waiting {int(wait_time)}s...")
                time.sleep(wait_time)
                continue
        
        if response.status_code != 200:
            print(f"⚠️  Error {response.status_code}: {response.text[:200]}")
            break
            
        data = response.json()
        if not data:
            break
            
        results.extend(data)
        page += 1
        
        # Progress indicator
        if page % 5 == 0:
            print(f"   ... fetched {len(results)} items")
        
        # Check if there are more pages
        if 'Link' not in response.headers or 'rel="next"' not in response.headers['Link']:
            break
    
    return results

def search_github(query, sort='created', order='desc'):
    """Use GitHub Search API with pagination"""
    url = f"{API_BASE}/search/issues"
    params = {
        'q': query,
        'sort': sort,
        'order': order,
        'per_page': 100
    }
    
    all_results = []
    page = 1
    
    while True:
        params['page'] = page
        response = requests.get(url, headers=headers, params=params)
        print(f" Searching GitHub: {query} (page {page})...")
        
        if response.status_code == 403 and 'rate limit' in response.text.lower():
            reset_time = int(response.headers.get('X-RateLimit-Reset', 0))
            if reset_time:
                wait_time = reset_time - time.time() + 5
                print(f"⏳ Rate limit hit. Waiting {int(wait_time)}s...")
                time.sleep(wait_time)
                continue
        
        if response.status_code != 200:
            print(f"⚠️  Search error {response.status_code}: {response.text[:200]}")
            break
        
        data = response.json()
        items = data.get('items', [])
        
        if not items:
            break
        
        all_results.extend(items)
        
        # GitHub Search API only returns first 1000 results
        if len(all_results) >= data.get('total_count', 0) or page >= 10:
            break
        
        page += 1
        time.sleep(0.5)  # Be nice to the API
    
    return all_results

def get_commits(org, repo, username, start_date, end_date):
    """Get all commits by the user - ALREADY FILTERED BY USER"""
    print(f"   Fetching commits by {username}...")
    url = f"{API_BASE}/repos/{org}/{repo}/commits"
    params = {
        "author": username,
        "since": start_date.isoformat(),
        "until": end_date.isoformat()
    }
    
    commits = fetch_all_pages(url, params)
    
    stats = {
        "total": len(commits),
        "by_month": defaultdict(int),
        "files_changed": 0,
        "additions": 0,
        "deletions": 0
    }
    
    print(f"   Fetching detailed stats for {len(commits)} commits...")
    
    # Batch process commit details
    for i, commit in enumerate(commits):
        date = datetime.strptime(commit['commit']['author']['date'], "%Y-%m-%dT%H:%M:%SZ")
        month_key = date.strftime("%Y-%m")
        stats['by_month'][month_key] += 1
        
        # Get detailed commit info for stats (only when needed)
        if (i + 1) % 50 == 0:
            print(f"   ... processed {i + 1}/{len(commits)} commits")
        
        commit_url = f"{API_BASE}/repos/{org}/{repo}/commits/{commit['sha']}"
        commit_detail = requests.get(commit_url, headers=headers).json()
        print(f" Fetching commit detail for {commit['sha']}")
        
        if 'stats' in commit_detail:
            stats['additions'] += commit_detail['stats'].get('additions', 0)
            stats['deletions'] += commit_detail['stats'].get('deletions', 0)
        if 'files' in commit_detail:
            stats['files_changed'] += len(commit_detail['files'])
        
        time.sleep(0.1)  # Small delay to avoid rate limiting
    
    return stats, commits

def get_pull_requests(org, repo, username, start_date, end_date):
    """Get PRs using Search API - FILTERED BY USER"""
    print(f"   Searching PRs created by {username}...")
    
    # Use GitHub Search API to filter by user upfront
    query = f"repo:{org}/{repo} author:{username} is:pr created:{start_date.strftime('%Y-%m-%d')}..{end_date.strftime('%Y-%m-%d')}"
    
    prs = search_github(query)
    
    stats = {
        "total": len(prs),
        "merged": 0,
        "closed": 0,
        "open": 0
    }
    
    # Count states
    for pr in prs:
        if pr.get('pull_request', {}).get('merged_at'):
            stats['merged'] += 1
        elif pr['state'] == 'closed':
            stats['closed'] += 1
        else:
            stats['open'] += 1
    
    return stats, prs

def get_pr_reviews(org, repo, username, start_date, end_date):
    """Get PR reviews using Search API - FILTERED BY USER"""
    print(f"   Searching PRs reviewed by {username}...")
    
    # Search for PRs where user was a reviewer
    query = f"repo:{org}/{repo} reviewed-by:{username} is:pr created:{start_date.strftime('%Y-%m-%d')}..{end_date.strftime('%Y-%m-%d')}"
    
    reviewed_prs = search_github(query)
    
    # Get actual review count for these PRs
    review_count = 0
    unique_prs = set()
    
    if reviewed_prs:
        print(f"   Counting reviews in {len(reviewed_prs)} PRs...")
        
        for pr in reviewed_prs:
            pr_number = pr['number']
            unique_prs.add(pr_number)
            
            # Get reviews for this PR
            reviews_url = f"{API_BASE}/repos/{org}/{repo}/pulls/{pr_number}/reviews"
            response = requests.get(reviews_url, headers=headers)
            print(f" Fetching reviews for PR #{pr_number} - Status: {response.status_code}")
            
            if response.status_code == 200:
                reviews = response.json()
                user_reviews = [r for r in reviews if r['user']['login'] == username]
                review_count += len(user_reviews)
            
            time.sleep(0.1)  # Small delay
    
    return {
        "total": review_count,
        "prs_reviewed": len(unique_prs)
    }

def get_issues(org, repo, username, start_date, end_date):
    """Get issues using Search API - FILTERED BY USER"""
    print(f"   Searching issues created by {username}...")
    
    # Search for issues (not PRs) created by user
    query = f"repo:{org}/{repo} author:{username} is:issue created:{start_date.strftime('%Y-%m-%d')}..{end_date.strftime('%Y-%m-%d')}"
    
    issues = search_github(query)
    
    stats = {
        "total": len(issues),
        "open": sum(1 for issue in issues if issue['state'] == 'open'),
        "closed": sum(1 for issue in issues if issue['state'] == 'closed')
    }
    
    return stats

def get_issue_comments(org, repo, username, start_date, end_date):
    """Get issue/PR comments by user"""
    print(f"   Searching comments by {username}...")
    
    # Search for comments by user
    query = f"repo:{org}/{repo} commenter:{username} created:{start_date.strftime('%Y-%m-%d')}..{end_date.strftime('%Y-%m-%d')}"
    
    # Note: GitHub Search doesn't directly support comment search, so we approximate
    # by searching for issues/PRs where user commented
    commented_items = search_github(query)
    
    return len(commented_items)

def generate_report(org, repo, username, year):
    """Generate the complete contribution report"""
    print(f"\n🔍 Analyzing contributions for {username} in {org}/{repo} ({year})")
    print("=" * 70)
    
    # Check rate limit before starting
    remaining = check_rate_limit()
    if remaining and remaining < 100:
        print("⚠️  Consider waiting for rate limit to reset\n")
    
    start_date, end_date = get_date_range(year)
    
    # Gather all statistics (now optimized with user filters)
    print("\n📊 Fetching data (this may take a few minutes)...\n")
    
    print("1️⃣  COMMITS")
    commit_stats, commits = get_commits(org, repo, username, start_date, end_date)
    
    print("\n2️⃣  PULL REQUESTS")
    pr_stats, prs = get_pull_requests(org, repo, username, start_date, end_date)
    
    print("\n3️⃣  CODE REVIEWS")
    review_stats = get_pr_reviews(org, repo, username, start_date, end_date)
    
    print("\n4️⃣  ISSUES")
    issue_stats = get_issues(org, repo, username, start_date, end_date)
    
    print("\n5️⃣  COMMENTS")
    comment_count = get_issue_comments(org, repo, username, start_date, end_date)
    
    print("\n" + "=" * 70)
    print(f"\n🎯 CONTRIBUTION REPORT - {year}")
    print(f"Repository: {org}/{repo}")
    print(f"Contributor: {username}")
    print("=" * 70)
    
    print(f"\n💻 COMMITS")
    print(f"  Total Commits: {commit_stats['total']}")
    print(f"  Files Changed: {commit_stats['files_changed']}")
    print(f"  Lines Added: +{commit_stats['additions']:,}")
    print(f"  Lines Deleted: -{commit_stats['deletions']:,}")
    print(f"  Net Change: {commit_stats['additions'] - commit_stats['deletions']:+,} lines")
    
    print(f"\n🔀 PULL REQUESTS")
    print(f"  Total PRs: {pr_stats['total']}")
    print(f"  Merged: {pr_stats['merged']} ✅")
    print(f"  Closed: {pr_stats['closed']}")
    print(f"  Open: {pr_stats['open']}")
    if pr_stats['total'] > 0:
        print(f"  Merge Rate: {(pr_stats['merged'] / pr_stats['total'] * 100):.1f}%")
    
    print(f"\n👀 CODE REVIEWS")
    print(f"  Reviews Given: {review_stats['total']}")
    print(f"  PRs Reviewed: {review_stats['prs_reviewed']}")
    
    print(f"\n🐛 ISSUES")
    print(f"  Total Issues: {issue_stats['total']}")
    print(f"  Open: {issue_stats['open']}")
    print(f"  Closed: {issue_stats['closed']}")
    
    print(f"\n💬 DISCUSSIONS")
    print(f"  Comments: {comment_count}")
    
    print("\n" + "=" * 70)
    
    # Generate social media text
    print("\n📱 SOCIAL MEDIA POST:")
    print("=" * 70)
    
    total_contributions = (commit_stats['total'] + pr_stats['total'] + 
                          review_stats['total'] + issue_stats['total'])
    
    social_text = f"""
🎯 My {year} Contributions to {org}/{repo}

💻 {commit_stats['total']} commits
📝 {commit_stats['additions']:,}+ / {commit_stats['deletions']:,}- lines of code
🔀 {pr_stats['merged']} PRs merged
👀 {review_stats['prs_reviewed']} PRs reviewed
🐛 {issue_stats['total']} issues created
💬 {comment_count} discussions participated

Total impact: {total_contributions} contributions! 🚀

#OpenSource #Developer #GitHub #{repo}
"""
    
    print(social_text)
    
    # Generate emoji visualization
    if commit_stats['by_month']:
        print("\n📊 ACTIVITY HEATMAP (by month):")
        print("=" * 70)
        months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 
                  'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
        
        max_commits = max(commit_stats['by_month'].values()) if commit_stats['by_month'] else 1
        
        for i, month in enumerate(months, 1):
            month_key = f"{year}-{i:02d}"
            count = commit_stats['by_month'].get(month_key, 0)
            
            # Scale bars based on max commits
            bar_length = int((count / max_commits) * 50) if max_commits > 0 else 0
            bar = "█" * bar_length if count > 0 else "░"
            
            print(f"{month}: {bar} ({count})")
    
    print("\n" + "=" * 70)
    
    # Final rate limit check
    remaining = check_rate_limit()
    if remaining:
        print(f"\n✅ API calls remaining: {remaining}")

if __name__ == "__main__":
    if not validate_config():
        exit(1)
    
    try:
        generate_report(ORGANIZATION, REPOSITORY, USERNAME, YEAR)
    except KeyboardInterrupt:
        print("\n\n⚠️  Script interrupted by user")
        exit(0)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        exit(1)