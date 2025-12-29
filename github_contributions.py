#!/usr/bin/env python3
import requests
from datetime import datetime
from collections import defaultdict
import os
import time
from dotenv import load_dotenv
from tqdm import tqdm

# Load environment variables
load_dotenv()

# Configuration from environment
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
USERNAME = os.getenv("GITHUB_USERNAME")
ORGANIZATION = os.getenv("GITHUB_ORG")
REPOSITORY = os.getenv("GITHUB_REPO")
YEAR = int(os.getenv("YEAR", datetime.now().year))

# GitHub API base URLs
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
        
        print(f"📊 API Rate Limits:")
        print(f"   REST API: {core['remaining']}/{core['limit']}")
        
        return core['remaining']
    return None

def get_date_range(year):
    """Get start and end dates for the year"""
    start_date = datetime(year, 1, 1)
    end_date = datetime(year, 12, 31, 23, 59, 59)
    return start_date, end_date

def get_commits(org, repo, username, start_date, end_date):
    """
    Commit fetching - get count fast, sample for details
    """
    print("💻 Fetching commit statistics...")
    
    # First, get commit list (lightweight)
    url = f"{API_BASE}/repos/{org}/{repo}/commits"
    params = {
        "author": username,
        "since": start_date.isoformat(),
        "until": end_date.isoformat(),
        "per_page": 100
    }
    
    all_commits = []
    page = 1
    
    with tqdm(desc="Loading commits", unit=" commits") as pbar:
        while page <= 20:  # Limit to 2000 commits max (20 pages)
            params['page'] = page
            response = requests.get(url, headers=headers, params=params)
            
            if response.status_code != 200:
                break
            
            commits = response.json()
            if not commits:
                break
            
            all_commits.extend(commits)
            pbar.update(len(commits))
            
            page += 1
            if 'Link' not in response.headers or 'rel="next"' not in response.headers['Link']:
                break
    
    # Build month stats
    stats = {
        "total": len(all_commits),
        "by_month": defaultdict(int),
        "additions": 0,
        "deletions": 0,
        "files_changed": 0
    }
    
    for commit in all_commits:
        date = datetime.strptime(commit['commit']['author']['date'], "%Y-%m-%dT%H:%M:%SZ")
        month_key = date.strftime("%Y-%m")
        stats['by_month'][month_key] += 1
    
    # Sample commits for detailed stats
    sample_size = min(30, len(all_commits))
    
    if sample_size > 0:
        print(f"   📊 Sampling {sample_size} commits for detailed stats...")
        
        # Get evenly distributed sample
        step = len(all_commits) // sample_size if sample_size > 0 else 1
        sample_commits = all_commits[::step][:sample_size]
        
        total_additions = 0
        total_deletions = 0
        total_files = 0
        
        with tqdm(total=sample_size, desc="Analyzing sample", unit=" commits") as pbar:
            for commit in sample_commits:
                commit_detail = requests.get(commit['url'], headers=headers).json()
                
                if 'stats' in commit_detail:
                    total_additions += commit_detail['stats'].get('additions', 0)
                    total_deletions += commit_detail['stats'].get('deletions', 0)
                
                if 'files' in commit_detail:
                    total_files += len(commit_detail['files'])
                
                pbar.update(1)
                time.sleep(0.05)  # Small delay
        
        # Extrapolate to all commits
        multiplier = len(all_commits) / sample_size
        stats['additions'] = int(total_additions * multiplier)
        stats['deletions'] = int(total_deletions * multiplier)
        stats['files_changed'] = int(total_files * multiplier)
    
    print(f"   ✅ Found {stats['total']} commits with ~{stats['additions']:,}/~{stats['deletions']:,} lines")
    
    return stats, all_commits

def get_pull_requests(org, repo, username, start_date, end_date):
    """
    Use GitHub Search API instead of pulls endpoint
    Search API properly filters by author from the start
    """
    print("   Using Search API (more reliable for filtering)...")
    
    # Use Search API with author filter
    query = f"repo:{org}/{repo} author:{username} is:pr created:{start_date.strftime('%Y-%m-%d')}..{end_date.strftime('%Y-%m-%d')}"
    
    search_url = f"{API_BASE}/search/issues"
    
    all_prs = []
    page = 1
    max_pages = 10  # Limit to 1000 results max
    
    with tqdm(desc="Searching PRs", unit=" PRs") as pbar:
        while page <= max_pages:
            params = {
                'q': query,
                'per_page': 100,
                'page': page
            }
            
            response = requests.get(search_url, headers=headers, params=params)
            
            if response.status_code != 200:
                print(f"   ⚠️  Search error {response.status_code}: {response.text[:100]}")
                break
            
            data = response.json()
            items = data.get('items', [])
            
            if not items:
                break
            
            all_prs.extend(items)
            pbar.update(len(items))
            
            # Check if we've got everything
            total_count = data.get('total_count', 0)
            if len(all_prs) >= total_count:
                break
            
            page += 1
            time.sleep(0.75)  # Search API has stricter rate limits
    
    stats = {
        "total": len(all_prs),
        "merged": 0,
        "closed": 0,
        "open": 0
    }
    
    # Count states - search returns issues, need to check pull_request field
    for pr in all_prs:
        # Search API returns merged_at in pull_request object
        pr_data = pr.get('pull_request', {})
        
        if pr_data.get('merged_at'):
            stats['merged'] += 1
        elif pr['state'] == 'closed':
            stats['closed'] += 1
        else:
            stats['open'] += 1
    
    print(f"   ✅ Found {stats['total']} PRs by {username} ({stats['merged']} merged)")
    
    return stats, all_prs

def get_pr_reviews(org, repo, username, start_date, end_date):
    """
    Review fetching - uses Search API then samples
    """
    print("👀 Fetching code reviews...")
    
    # Use search API to find PRs where user participated
    query = f"repo:{org}/{repo} reviewed-by:{username} -assignee:{username} created:{start_date.strftime('%Y-%m-%d')}..{end_date.strftime('%Y-%m-%d')}"
    
    search_url = f"{API_BASE}/search/issues"
    params = {
        'q': query,
        'per_page': 100
    }
    
    all_reviewed_prs = []
    page = 1
    max_pages = 10  # Limit to 1000 PRs (10 pages of 100)
    
    with tqdm(desc="Finding reviewed PRs", unit=" PRs") as pbar:
        while page <= max_pages:
            params['page'] = page
            response = requests.get(search_url, headers=headers, params=params)
            
            if response.status_code != 200:
                print(f"   ⚠️  Search error: {response.status_code}")
                break
            
            data = response.json()
            items = data.get('items', [])
            
            if not items:
                break
            
            all_reviewed_prs.extend(items)
            pbar.update(len(items))
            
            # Stop if we've reached total count
            if len(all_reviewed_prs) >= data.get('total_count', 0):
                break
            
            page += 1
            time.sleep(0.5)  # Rate limit protection
    
    # Count actual reviews by sampling
    review_count = 0
    unique_prs = len(all_reviewed_prs)
    
    # Sample strategy: Check up to 50 PRs, extrapolate the rest
    sample_size = min(50, unique_prs)
    
    if sample_size > 0:
        with tqdm(total=sample_size, desc="Counting reviews", unit=" PRs") as pbar:
            for pr in all_reviewed_prs[:sample_size]:
                reviews_url = f"{API_BASE}/repos/{org}/{repo}/pulls/{pr['number']}/reviews"
                response = requests.get(reviews_url, headers=headers)
                
                if response.status_code == 200:
                    reviews = response.json()
                    user_reviews = [r for r in reviews if r['user']['login'].lower() == username.lower()]
                    review_count += len(user_reviews)
                
                pbar.update(1)
                time.sleep(0.05)
        
        # Extrapolate to all PRs if we sampled
        if unique_prs > sample_size:
            avg_reviews_per_pr = review_count / sample_size
            review_count = int(avg_reviews_per_pr * unique_prs)
            print(f"   📊 Extrapolated from {sample_size} PRs")
    
    print(f"   ✅ Found ~{review_count} reviews across {unique_prs} PRs")
    
    return {
        "total": review_count,
        "prs_reviewed": unique_prs
    }

def get_issues(org, repo, username, start_date, end_date):
    """Get issues using Search API"""
    print("🐛 Fetching issues...")
    
    query = f"repo:{org}/{repo} author:{username} is:issue created:{start_date.strftime('%Y-%m-%d')}..{end_date.strftime('%Y-%m-%d')}"
    
    search_url = f"{API_BASE}/search/issues"
    params = {'q': query, 'per_page': 100}
    
    with tqdm(desc="Loading issues", bar_format='{l_bar}{bar}| {n_fmt}/{total_fmt}') as pbar:
        response = requests.get(search_url, headers=headers, params=params)
        pbar.update(100)
    
    if response.status_code != 200:
        return {"total": 0, "open": 0, "closed": 0}
    
    issues = response.json().get('items', [])
    
    stats = {
        "total": len(issues),
        "open": sum(1 for issue in issues if issue['state'] == 'open'),
        "closed": sum(1 for issue in issues if issue['state'] == 'closed')
    }
    
    print(f"   ✅ Found {stats['total']} issues")
    
    return stats

def get_comments_count(org, repo, username, start_date, end_date):
    """Get approximate comment count"""
    print("💬 Fetching comment activity...")
    
    query = f"repo:{org}/{repo} commenter:{username} created:{start_date.strftime('%Y-%m-%d')}..{end_date.strftime('%Y-%m-%d')}"
    
    search_url = f"{API_BASE}/search/issues"
    params = {'q': query, 'per_page': 1}
    
    with tqdm(desc="Counting comments", bar_format='{l_bar}{bar}| {n_fmt}/{total_fmt}') as pbar:
        response = requests.get(search_url, headers=headers, params=params)
        pbar.update(100)
    
    if response.status_code != 200:
        return 0
    
    count = response.json().get('total_count', 0)
    print(f"   ✅ Found ~{count} commented threads")
    
    return count

def generate_report(org, repo, username, year):
    """Generate the complete contribution report"""
    print("\n" + "=" * 70)
    print(f"🔍 GitHub Contribution Report Generator")
    print(f"Repository: {org}/{repo}")
    print(f"User: {username}")
    print(f"Year: {year}")
    print("=" * 70 + "\n")
    
    # Check rate limit
    check_rate_limit()
    print()
    
    start_date, end_date = get_date_range(year)
    
    # Track total API calls
    start_time = time.time()
    
    # Gather all statistics with progress tracking
    print("📊 Gathering contribution data...\n")
    
    commit_stats, _ = get_commits(org, repo, username, start_date, end_date)
    print()
    
    pr_stats, _ = get_pull_requests(org, repo, username, start_date, end_date)
    print()
    
    review_stats = get_pr_reviews(org, repo, username, start_date, end_date)
    print()
    
    issue_stats = get_issues(org, repo, username, start_date, end_date)
    print()
    
    comment_count = get_comments_count(org, repo, username, start_date, end_date)
    print()
    
    elapsed_time = time.time() - start_time
    
    # Generate report
    print("\n" + "=" * 70)
    print(f"🎯 CONTRIBUTION REPORT - {year}")
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
    
    # Social media post
    total_contributions = (commit_stats['total'] + pr_stats['total'] + 
                          review_stats['total'] + issue_stats['total'])
    
    print("\n📱 SOCIAL MEDIA POST:")
    print("=" * 70)
    
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
    
    # Activity heatmap
    if commit_stats['by_month']:
        print("\n📊 ACTIVITY HEATMAP (by month):")
        print("=" * 70)
        months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 
                  'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
        
        max_commits = max(commit_stats['by_month'].values()) if commit_stats['by_month'] else 1
        
        for i, month in enumerate(months, 1):
            month_key = f"{year}-{i:02d}"
            count = commit_stats['by_month'].get(month_key, 0)
            
            bar_length = int((count / max_commits) * 50) if max_commits > 0 else 0
            bar = "█" * bar_length if count > 0 else "░"
            
            print(f"{month}: {bar} ({count})")
    
    print("\n" + "=" * 70)
    print(f"\n⏱️  Report generated in {elapsed_time:.2f} seconds")
    
    # Final rate limit check
    remaining = check_rate_limit()

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