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
    
    # Get detailed stats for ALL commits
    if len(all_commits) > 0:
        print(f"   📊 Fetching detailed stats for all {len(all_commits)} commits...")
        
        total_additions = 0
        total_deletions = 0
        total_files = 0
        
        with tqdm(total=len(all_commits), desc="Analyzing commits", unit=" commits") as pbar:
            for commit in all_commits:
                commit_detail = requests.get(commit['url'], headers=headers).json()
                
                if 'stats' in commit_detail:
                    total_additions += commit_detail['stats'].get('additions', 0)
                    total_deletions += commit_detail['stats'].get('deletions', 0)
                
                if 'files' in commit_detail:
                    total_files += len(commit_detail['files'])
                
                pbar.update(1)
                time.sleep(0.05)  # Small delay to avoid rate limiting
        
        stats['additions'] = total_additions
        stats['deletions'] = total_deletions
        stats['files_changed'] = total_files
    
    print(f"   ✅ Found {stats['total']} commits with {stats['additions']:,}/{stats['deletions']:,} lines")
    
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

def generate_html_report(org, repo, username, year, commit_stats, pr_stats, review_stats, issue_stats, comment_count):
    """Generate a beautiful HTML report for social media"""
    
    total_contributions = (commit_stats['total'] + pr_stats['total'] + 
                          review_stats['total'] + issue_stats['total'])
    
    # Calculate monthly percentages for heatmap
    months_data = []
    max_commits = max(commit_stats['by_month'].values()) if commit_stats['by_month'] else 1
    month_names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 
                   'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    
    for i, month in enumerate(month_names, 1):
        month_key = f"{year}-{i:02d}"
        count = commit_stats['by_month'].get(month_key, 0)
        percentage = (count / max_commits * 100) if max_commits > 0 else 0
        months_data.append({
            'name': month,
            'count': count,
            'percentage': percentage
        })
    
    merge_rate = (pr_stats['merged'] / pr_stats['total'] * 100) if pr_stats['total'] > 0 else 0
    
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{year} GitHub Contributions - {username}</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            background: linear-gradient(135deg, #0b1955 0%, #150a20 100%);
            color: #fff;
            padding: 2rem;
            min-height: 100vh;
        }}

        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background: rgba(255, 255, 255, 0.1);
            backdrop-filter: blur(10px);
            border-radius: 20px;
            padding: 3rem;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
        }}

        .header {{
            text-align: center;
            margin-bottom: 3rem;
        }}

        .header h1 {{
            font-size: 3rem;
            font-weight: 800;
            margin-bottom: 0.5rem;
            text-shadow: 2px 2px 4px rgba(0, 0, 0, 0.3);
        }}

        .header .year {{
            font-size: 4rem;
            font-weight: 900;
            background: linear-gradient(45deg, #FFD700, #FFA500);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }}
        
        .footer {{
            text-align: center;
            margin-top: 2rem;
            padding-top: 2rem;
            border-top: 2px solid rgba(255, 255, 255, 0.2);
            opacity: 0.8;
        }}

        .github-link {{
            color: #FFD700;
            text-decoration: none;
            font-weight: 600;
            transition: all 0.3s ease;
        }}

        .github-link:hover {{
            color: #FFA500;
            text-decoration: underline;
        }}

        .repo-info {{
            text-align: center;
            margin-bottom: 2rem;
            padding: 1rem;
            background: rgba(0, 0, 0, 0.2);
            border-radius: 10px;
        }}

        .repo-info h2 {{
            font-size: 1.5rem;
            font-weight: 600;
        }}

        .repo-info .contributor {{
            font-size: 1.2rem;
            opacity: 0.9;
            margin-top: 0.5rem;
        }}

        .cards-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 1.5rem;
            margin-bottom: 3rem;
        }}

        .card {{
            background: rgba(255, 255, 255, 0.15);
            padding: 2rem;
            border-radius: 15px;
            text-align: center;
            transition: transform 0.3s ease, box-shadow 0.3s ease;
            border: 2px solid rgba(255, 255, 255, 0.2);
        }}

        .card:hover {{
            transform: translateY(-5px);
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.3);
        }}

        .card .icon {{
            font-size: 2.5rem;
            margin-bottom: 1rem;
        }}

        .card .number {{
            font-size: 3rem;
            font-weight: 900;
            margin-bottom: 0.5rem;
            background: linear-gradient(45deg, #FFD700, #FFA500);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }}

        .card .label {{
            font-size: 0.9rem;
            opacity: 0.9;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 1px;
        }}

        .card .subtitle {{
            font-size: 0.8rem;
            opacity: 0.7;
            margin-top: 0.5rem;
        }}

        .section {{
            margin-bottom: 2.5rem;
            background: rgba(255, 255, 255, 0.1);
            padding: 2rem;
            border-radius: 15px;
        }}

        .section:last-child {{
            margin-bottom: 0;
        }}

        .section h3 {{
            font-size: 1.5rem;
            margin-bottom: 1.5rem;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }}

        .heatmap {{
            display: flex;
            flex-direction: column;
            gap: 0.5rem;
        }}

        .heatmap-row {{
            display: flex;
            align-items: center;
            gap: 1rem;
        }}

        .month-label {{
            width: 40px;
            font-weight: 600;
            font-size: 0.9rem;
        }}

        .month-bar {{
            flex: 1;
            background: rgba(0, 0, 0, 0.2);
            border-radius: 5px;
            height: 25px;
            position: relative;
            overflow: hidden;
        }}

        .month-bar-fill {{
            height: 100%;
            background: linear-gradient(90deg, #43a598, #306ad6);
            display: flex;
            align-items: center;
            padding-left: 10px;
            font-size: 0.85rem;
            font-weight: 600;
            transition: width 0.8s ease;
        }}

        .social-post {{
            background: rgba(0, 0, 0, 0.3);
            padding: 2rem;
            border-radius: 15px;
            font-size: 1.1rem;
            line-height: 1.8;
            text-align: center;
        }}

        .social-post .emoji-line {{
            margin: 0.5rem 0;
        }}

        .highlight {{
            color: #FFD700;
            font-weight: 700;
        }}

        .impact-number {{
            font-size: 4rem;
            font-weight: 900;
            color: #FFD700;
            text-shadow: 2px 2px 8px rgba(0, 0, 0, 0.4);
        }}

        .progress-bar {{
            background: rgba(0, 0, 0, 0.3);
            height: 30px;
            border-radius: 15px;
            overflow: hidden;
            margin-top: 1rem;
        }}

        .progress-fill {{
            height: 100%;
            background: linear-gradient(90deg, #4ade80, #22c55e);
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 700;
            font-size: 0.9rem;
            transition: width 1s ease;
        }}

        @media (max-width: 768px) {{
            .container {{
                padding: 1.5rem;
            }}

            .header h1 {{
                font-size: 2rem;
            }}

            .header .year {{
                font-size: 3rem;
            }}

            .card .number {{
                font-size: 2rem;
            }}

            .cards-grid {{
                grid-template-columns: 1fr;
            }}
        }}

        @media print {{
            body {{
                background: white;
            }}
            
            .container {{
                background: white;
                color: #333;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="year">{year}</div>
            <h1>GitHub Contribution Report</h1>
        </div>

        <div class="repo-info">
            <h2>🚀 {org}/{repo}</h2>
            <div class="contributor">👨‍💻 {username}</div>
        </div>

        <div class="cards-grid">
            <div class="card">
                <div class="icon">💻</div>
                <div class="number">{commit_stats['total']}</div>
                <div class="label">Commits</div>
                <div class="subtitle">{commit_stats['files_changed']:,} files changed</div>
            </div>

            <div class="card">
                <div class="icon">🔀</div>
                <div class="number">{pr_stats['total']}</div>
                <div class="label">Pull Requests</div>
                <div class="subtitle">{pr_stats['merged']} merged ✅</div>
            </div>

            <div class="card">
                <div class="icon">👀</div>
                <div class="number">{review_stats['total']:,}</div>
                <div class="label">Code Reviews</div>
                <div class="subtitle">{review_stats['prs_reviewed']} PRs reviewed</div>
            </div>

            <div class="card">
                <div class="icon">📝</div>
                <div class="number">{abs(commit_stats['additions'] - commit_stats['deletions']) // 1000}K+</div>
                <div class="label">Net Lines</div>
                <div class="subtitle">+{commit_stats['additions']:,} / -{commit_stats['deletions']:,}</div>
            </div>

            <div class="card">
                <div class="icon">💬</div>
                <div class="number">{comment_count}</div>
                <div class="label">Discussions</div>
                <div class="subtitle">{issue_stats['total']} issues created</div>
            </div>

            <div class="card">
                <div class="icon">🎯</div>
                <div class="number">{total_contributions:,}</div>
                <div class="label">Total Impact</div>
                <div class="subtitle">{merge_rate:.1f}% merge rate</div>
            </div>
        </div>

        <div class="section">
            <h3><span>📊</span> Monthly Activity</h3>
            <div class="heatmap">
"""
    
    # Add monthly heatmap
    for month_data in months_data:
        html_content += f"""                <div class="heatmap-row">
                    <div class="month-label">{month_data['name']}</div>
                    <div class="month-bar">
                        <div class="month-bar-fill" style="width: {month_data['percentage']}%">{month_data['count']}</div>
                    </div>
                </div>
"""
    
    html_content += f"""            </div>
        </div>

        <div class="section">
            <h3><span>🔀</span> Pull Request Success</h3>
            <div class="progress-bar">
                <div class="progress-fill" style="width: {merge_rate}%">{merge_rate:.1f}% Merge Rate</div>
            </div>
            <div style="margin-top: 1rem; text-align: center; opacity: 0.9;">
                <span style="color: #4ade80;">✅ {pr_stats['merged']} Merged</span> • 
                <span style="color: #f87171;">❌ {pr_stats['closed']} Closed</span> • 
                <span style="color: #60a5fa;">⏳ {pr_stats['open']} Open</span>
            </div>
        </div>

        <div class="section">
            <h3><span>📱</span> Summary</h3>
            <div class="social-post">
                <div style="margin-bottom: 1.5rem;">
                    <div class="impact-number">{total_contributions:,}</div>
                    <div style="font-size: 1.2rem; margin-top: 0.5rem;">Total Contributions 🚀</div>
                </div>
                <div class="emoji-line">💻 <span class="highlight">{commit_stats['total']}</span> commits</div>
                <div class="emoji-line">📝 <span class="highlight">{commit_stats['additions']:,}+</span> / <span class="highlight">{commit_stats['deletions']:,}-</span> lines of code</div>
                <div class="emoji-line">🔀 <span class="highlight">{pr_stats['merged']}</span> PRs merged</div>
                <div class="emoji-line">👀 <span class="highlight">{review_stats['prs_reviewed']}</span> PRs reviewed</div>
                <div class="emoji-line">🐛 <span class="highlight">{issue_stats['total']}</span> issues created</div>
                <div class="emoji-line">💬 <span class="highlight">{comment_count}</span> discussions participated</div>
            </div>
        </div>

        <div class="footer">
            <p style="margin-top: 0.5rem;">
                <a href="https://github.com/{username}" target="_blank" class="github-link">
                    @{username}
                </a> • {datetime.now().strftime('%B %d, %Y')}
            </p>
        </div>
    </div>

    <script>
        // Add smooth animations on load
        window.addEventListener('load', () => {{
            const bars = document.querySelectorAll('.month-bar-fill, .progress-fill');
            bars.forEach(bar => {{
                const width = bar.style.width;
                bar.style.width = '0%';
                setTimeout(() => {{
                    bar.style.width = width;
                }}, 100);
            }});
        }});
    </script>
</body>
</html>"""
    
    return html_content

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
    
    # Generate HTML report
    print("   📄 Creating HTML report...")
    html_content = generate_html_report(
        org, repo, username, year,
        commit_stats, pr_stats, review_stats, issue_stats, comment_count
    )
    
    # Create output directory if not exists
    os.makedirs("outputs", exist_ok=True)
    
    html_filename = f"outputs/github_report_{username}_{year}.html"
    with open(html_filename, 'w', encoding='utf-8') as f:
        f.write(html_content)
    print(f"   ✅ HTML saved: {html_filename}")
    
    # Generate quick terminal report
    total_contributions = (commit_stats['total'] + pr_stats['total'] + 
                          review_stats['total'] + issue_stats['total'])
    
    print("\n" + "=" * 70)
    print(f"📊 QUICK SUMMARY")
    print("=" * 70)
    print(f"💻 Commits: {commit_stats['total']}")
    print(f"🔀 Pull Requests: {pr_stats['total']} ({pr_stats['merged']} merged)")
    print(f"👀 Code Reviews: {review_stats['total']:,} reviews in {review_stats['prs_reviewed']} PRs")
    print(f"📝 Code Changes: +{commit_stats['additions']:,} / -{commit_stats['deletions']:,} lines")
    print(f"💬 Discussions: {comment_count} comments")
    print(f"🎯 Total Impact: {total_contributions:,} contributions")
    
    print("\n" + "=" * 70)
    print(f"⏱️  Report generated in {elapsed_time:.2f} seconds")
    
    # Final message
    print("\n" + "=" * 70)
    print("📸 Take a screenshot to share on social media!")
    print("=" * 70)

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