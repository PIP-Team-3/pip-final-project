#!/usr/bin/env python3
"""
P2N Management CLI - Simple commands for common tasks
Usage: python manage.py <command>

Commands:
  env           Print all environment variables (loads from .env)
  models        Show/set current model configuration
  set-extractor <model>   Set extractor model (gpt-4o, o3-mini)
  set-planner <model>     Set planner model (o3-mini, gpt-5)
  pwsh-env      Generate PowerShell command to load .env
  start         Start the API server (auto-loads .env)
  health        Check API health
  download      Download all 20 papers to uploads/
  upload        Upload all papers to API
  smoke <id>    Run smoke test pipeline on a paper
  list          List all ingested papers
  extract <id>  Extract claims from a paper
  plan <id>     Generate plan for a paper
  run <id>      Execute a plan
  report <id>   Generate report for a paper
"""

import sys
import subprocess
import json
import os
from pathlib import Path

API_URL = "http://localhost:8000"

def load_env():
    """Load .env file and return environment dict"""
    env = os.environ.copy()
    env_file = Path(".env")
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    env[key.strip()] = value.strip().strip('"').strip("'")
    return env

def print_env():
    """Print environment variables from .env"""
    env = load_env()
    env_file = Path(".env")

    if not env_file.exists():
        print("✗ No .env file found")
        return

    print("=== Environment Variables (from .env) ===\n")

    # Important vars to check
    important = ["OPENAI_API_KEY", "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_ANON_KEY"]

    for key in important:
        value = env.get(key, "NOT SET")
        if value != "NOT SET":
            # Redact secrets
            if "KEY" in key or "SECRET" in key:
                display = value[:8] + "..." if len(value) > 8 else "***"
            else:
                display = value
            print(f"{key:30} = {display}")
        else:
            print(f"{key:30} = ⚠ NOT SET")

    print(f"\n✓ Total vars in .env: {len([l for l in env_file.read_text().split('\n') if '=' in l and not l.startswith('#')])}")

def start_server():
    """Start the API server with environment variables loaded"""
    print("Starting API server...")
    print("Loading .env and starting server...")
    print("Press Ctrl+C to stop\n")

    env = load_env()
    env_file = Path(".env")

    if env_file.exists():
        print("✓ Loading .env file")
    else:
        print("⚠ No .env file found - using system environment variables")

    subprocess.run([
        sys.executable, "-m", "uvicorn",
        "app.main:app",
        "--app-dir", "api",
        "--log-level", "info",
        "--workers", "1"
    ], env=env)

def check_health():
    """Check API health"""
    try:
        import requests
        resp = requests.get(f"{API_URL}/health", timeout=5)
        if resp.status_code == 200:
            print("✓ API is healthy")
            print(json.dumps(resp.json(), indent=2))
            return True
        else:
            print(f"✗ API returned {resp.status_code}")
            return False
    except Exception as e:
        print(f"✗ API is not running: {e}")
        return False

def download_papers():
    """Download papers using PowerShell script"""
    print("Downloading 20 papers from arXiv...")
    if os.name == 'nt':  # Windows
        subprocess.run(["powershell", "-ExecutionPolicy", "Bypass", "-File", "scripts/download_papers.ps1"])
    else:
        subprocess.run(["bash", "scripts/download_papers.sh"])

def upload_papers():
    """Upload papers using bash script"""
    print("Uploading papers to API...")
    subprocess.run(["bash", "scripts/upload_papers.sh"])

def smoke_test(paper_id):
    """Run full smoke pipeline on a paper"""
    try:
        import requests

        print(f"→ Running smoke pipeline on paper: {paper_id}\n")

        # Extract
        print("Step 1/5: Extracting claims...")
        resp = requests.post(f"{API_URL}/api/v1/papers/{paper_id}/extract", stream=True, timeout=120)
        claims = None
        for line in resp.iter_lines():
            if line.startswith(b'data: '):
                data = json.loads(line[6:])
                if 'claims' in data:
                    claims = data['claims']
                    print(f"✓ Extracted {len(claims)} claims\n")

        if not claims:
            print("✗ No claims found")
            return

        # Plan
        print("Step 2/5: Generating plan (budget=15)...")
        plan_resp = requests.post(
            f"{API_URL}/api/v1/papers/{paper_id}/plan",
            json={"claims": claims[:3], "budget_minutes": 15},
            timeout=120
        ).json()
        plan_id = plan_resp['plan_id']
        print(f"✓ Plan created: {plan_id}\n")

        # Materialize
        print("Step 3/5: Materializing notebook...")
        mat_resp = requests.post(f"{API_URL}/api/v1/plans/{plan_id}/materialize", timeout=120).json()
        print(f"✓ Materialized (env_hash: {mat_resp['env_hash'][:8]}...)\n")

        # Run
        print("Step 4/5: Starting run...")
        run_resp = requests.post(f"{API_URL}/api/v1/plans/{plan_id}/run", timeout=10).json()
        run_id = run_resp['run_id']
        print(f"✓ Run started: {run_id}\n")

        # Report
        print("Step 5/5: Generating report...")
        report = requests.get(f"{API_URL}/api/v1/papers/{paper_id}/report", timeout=30).json()
        print(f"✓ Report generated (gap: {report.get('gap_percent', 'N/A')}%)\n")

        print("=== Smoke Pipeline Complete ===")
        print(f"Paper: {paper_id}")
        print(f"Plan: {plan_id}")
        print(f"Run: {run_id}")

    except Exception as e:
        print(f"✗ Error: {e}")

def list_papers():
    """List all papers"""
    if Path("upload_results.txt").exists():
        print("=== Uploaded Papers ===")
        with open("upload_results.txt") as f:
            for line in f:
                paper_id, title = line.strip().split('|', 1)
                print(f"{paper_id}  # {title}")
    else:
        print("No upload_results.txt found. Run 'python manage.py upload' first.")

def extract_claims(paper_id):
    """Extract claims from a paper"""
    try:
        import requests
        print(f"Extracting claims from {paper_id}...")
        resp = requests.post(f"{API_URL}/api/v1/papers/{paper_id}/extract", stream=True, timeout=120)
        for line in resp.iter_lines():
            if line.startswith(b'data: '):
                data = json.loads(line[6:])
                if 'claims' in data:
                    print(json.dumps(data['claims'], indent=2))
    except Exception as e:
        print(f"✗ Error: {e}")

def generate_plan(paper_id):
    """Generate plan for a paper"""
    try:
        import requests
        print(f"Generating plan for {paper_id}...")
        # First get claims
        resp = requests.post(f"{API_URL}/api/v1/papers/{paper_id}/extract", stream=True, timeout=120)
        claims = None
        for line in resp.iter_lines():
            if line.startswith(b'data: '):
                data = json.loads(line[6:])
                if 'claims' in data:
                    claims = data['claims']

        if claims:
            plan_resp = requests.post(
                f"{API_URL}/api/v1/papers/{paper_id}/plan",
                json={"claims": claims[:3], "budget_minutes": 15},
                timeout=120
            ).json()
            print(f"✓ Plan created: {plan_resp['plan_id']}")
        else:
            print("✗ No claims found")
    except Exception as e:
        print(f"✗ Error: {e}")

def run_plan(plan_id):
    """Execute a plan"""
    try:
        import requests
        print(f"Running plan {plan_id}...")
        resp = requests.post(f"{API_URL}/api/v1/plans/{plan_id}/run", timeout=10).json()
        print(f"✓ Run started: {resp['run_id']}")
    except Exception as e:
        print(f"✗ Error: {e}")

def generate_report(paper_id):
    """Generate report for a paper"""
    try:
        import requests
        print(f"Generating report for {paper_id}...")
        resp = requests.get(f"{API_URL}/api/v1/papers/{paper_id}/report", timeout=30).json()
        print(json.dumps(resp, indent=2))
    except Exception as e:
        print(f"✗ Error: {e}")

def show_models():
    """Show current model configuration"""
    env = load_env()

    print("=== Current Model Configuration ===\n")
    print(f"Extractor Model:  {env.get('OPENAI_EXTRACTOR_MODEL', 'gpt-4o (default)')}")
    print(f"Planner Model:    {env.get('OPENAI_PLANNER_MODEL', 'o3-mini (default)')}")
    print(f"\nAvailable Models:")
    print("  Extractor: gpt-4o, o3-mini")
    print("  Planner:   o3-mini, gpt-5")
    print(f"\nTo change models:")
    print("  python manage.py set-extractor <model>")
    print("  python manage.py set-planner <model>")

def set_extractor_model(model):
    """Set extractor model in .env"""
    valid_models = ["gpt-4o", "o3-mini"]
    if model not in valid_models:
        print(f"✗ Invalid model: {model}")
        print(f"  Valid options: {', '.join(valid_models)}")
        return

    update_env_var("OPENAI_EXTRACTOR_MODEL", model)
    print(f"✓ Extractor model set to: {model}")
    print("  Restart server for changes to take effect")

def set_planner_model(model):
    """Set planner model in .env"""
    valid_models = ["o3-mini", "gpt-5"]
    if model not in valid_models:
        print(f"✗ Invalid model: {model}")
        print(f"  Valid options: {', '.join(valid_models)}")
        return

    update_env_var("OPENAI_PLANNER_MODEL", model)
    print(f"✓ Planner model set to: {model}")
    print("  Restart server for changes to take effect")

def update_env_var(key, value):
    """Update or add environment variable in .env file"""
    env_file = Path(".env")
    if not env_file.exists():
        print("✗ No .env file found")
        return

    lines = env_file.read_text().splitlines()
    found = False

    for i, line in enumerate(lines):
        if line.strip().startswith(f"{key}="):
            lines[i] = f"{key}={value}"
            found = True
            break

    if not found:
        lines.append(f"{key}={value}")

    env_file.write_text('\n'.join(lines) + '\n')

def generate_pwsh_env_loader():
    """Generate PowerShell command to load .env"""
    print("=== PowerShell .env Loader ===\n")
    print("Copy and paste this into PowerShell to load .env:\n")
    print(r'Get-Content .env | % { if ($_ -match \'^\s*([^#=]+)=(.*)$\') { Set-Item -Path (\'Env:\' + $matches[1].Trim()) -Value ($matches[2].Trim().Trim(\'"\')) } }')
    print("\nOr run this command directly:")
    print("  python manage.py pwsh-env | powershell -Command -")
    print("\nTo verify it worked:")
    print("  $env:OPENAI_API_KEY")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1]

    if command == "env":
        print_env()
    elif command == "models":
        show_models()
    elif command == "set-extractor":
        if len(sys.argv) < 3:
            print("Usage: python manage.py set-extractor <model>")
            print("Valid models: gpt-4o, o3-mini")
            sys.exit(1)
        set_extractor_model(sys.argv[2])
    elif command == "set-planner":
        if len(sys.argv) < 3:
            print("Usage: python manage.py set-planner <model>")
            print("Valid models: o3-mini, gpt-5")
            sys.exit(1)
        set_planner_model(sys.argv[2])
    elif command == "pwsh-env":
        generate_pwsh_env_loader()
    elif command == "start":
        start_server()
    elif command == "health":
        check_health()
    elif command == "download":
        download_papers()
    elif command == "upload":
        upload_papers()
    elif command == "smoke":
        if len(sys.argv) < 3:
            print("Usage: python manage.py smoke <paper_id>")
            sys.exit(1)
        smoke_test(sys.argv[2])
    elif command == "list":
        list_papers()
    elif command == "extract":
        if len(sys.argv) < 3:
            print("Usage: python manage.py extract <paper_id>")
            sys.exit(1)
        extract_claims(sys.argv[2])
    elif command == "plan":
        if len(sys.argv) < 3:
            print("Usage: python manage.py plan <paper_id>")
            sys.exit(1)
        generate_plan(sys.argv[2])
    elif command == "run":
        if len(sys.argv) < 3:
            print("Usage: python manage.py run <plan_id>")
            sys.exit(1)
        run_plan(sys.argv[2])
    elif command == "report":
        if len(sys.argv) < 3:
            print("Usage: python manage.py report <paper_id>")
            sys.exit(1)
        generate_report(sys.argv[2])
    else:
        print(f"Unknown command: {command}")
        print(__doc__)
        sys.exit(1)
