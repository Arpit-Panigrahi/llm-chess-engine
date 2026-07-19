#!/usr/bin/env python3
"""
check_ollama_env.py — Diagnose Ollama runtime environment.

Detects local/Docker/WSL mode, tests connectivity, checks model availability,
and provides mode-specific remediation steps.

Usage:
  python scripts/check_ollama_env.py
  python scripts/check_ollama_env.py --url http://host.docker.internal:11434
  python scripts/check_ollama_env.py --help
"""

import argparse
import json
import os
import platform
import subprocess
import sys

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


def detect_mode():
    """Detect runtime mode: local, docker, wsl, or unknown."""
    mode = "local"
    details = []

    # ── WSL Detection ────────────────────────────────────
    is_wsl = False
    try:
        with open("/proc/version", "r") as f:
            version_str = f.read().lower()
            if "microsoft" in version_str or "wsl" in version_str:
                is_wsl = True
                details.append("WSL detected via /proc/version")
    except FileNotFoundError:
        pass

    if is_wsl:
        mode = "wsl"

    # ── Docker Detection ─────────────────────────────────
    is_docker = False
    if os.path.exists("/.dockerenv"):
        is_docker = True
        details.append("Docker detected via /.dockerenv")
    else:
        try:
            with open("/proc/1/cgroup", "r") as f:
                if "docker" in f.read():
                    is_docker = True
                    details.append("Docker detected via /proc/1/cgroup")
        except FileNotFoundError:
            pass

    if is_docker:
        mode = "docker"

    # ── OS Info ──────────────────────────────────────────
    details.append(f"Platform: {platform.system()} {platform.release()}")
    details.append(f"Python: {platform.python_version()}")

    return mode, details


def check_connectivity(base_url, timeout=5):
    """Test Ollama API connectivity."""
    if not HAS_REQUESTS:
        return False, "Python 'requests' library not installed. Run: pip install requests"

    url = f"{base_url}/api/tags"
    try:
        resp = requests.get(url, timeout=timeout)
        resp.raise_for_status()
        return True, f"Connected to {base_url} (HTTP {resp.status_code})"
    except requests.ConnectionError:
        return False, f"Cannot connect to {base_url} (connection refused)"
    except requests.Timeout:
        return False, f"Timeout connecting to {base_url} after {timeout}s"
    except requests.HTTPError as e:
        return False, f"HTTP error from {base_url}: {e}"
    except Exception as e:
        return False, f"Unexpected error: {e}"


def check_models(base_url, required_model="llama3"):
    """Check if the required model is available."""
    if not HAS_REQUESTS:
        return False, [], "Cannot check models (requests library missing)"

    url = f"{base_url}/api/tags"
    try:
        resp = requests.get(url, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        models = data.get("models", [])
        model_names = [m.get("name", "") for m in models]
        short_names = [n.split(":")[0] for n in model_names]

        found = required_model in short_names or required_model in model_names
        return found, model_names, ""
    except Exception as e:
        return False, [], str(e)


def check_ollama_process():
    """Check if Ollama is running as a local process."""
    try:
        result = subprocess.run(["pgrep", "-f", "ollama"], capture_output=True, text=True)
        return result.returncode == 0
    except FileNotFoundError:
        # pgrep not available
        try:
            result = subprocess.run(["ps", "aux"], capture_output=True, text=True)
            return "ollama" in result.stdout.lower()
        except Exception:
            return False


def get_wsl_host_ip():
    """Get the Windows host IP from WSL."""
    try:
        with open("/etc/resolv.conf", "r") as f:
            for line in f:
                if line.strip().startswith("nameserver"):
                    return line.strip().split()[-1]
    except FileNotFoundError:
        pass
    return None


def print_remediation(mode, connected, base_url):
    """Print mode-specific remediation steps."""
    if connected:
        return

    print("\n🔧 REMEDIATION STEPS")
    print("─" * 50)

    if mode == "local":
        print("""
  Your setup: Native Linux/macOS running Ollama locally.

  1. Install Ollama (if not installed):
     curl -fsSL https://ollama.com/install.sh | sh

  2. Start the Ollama server:
     ollama serve

  3. Pull the required model:
     ollama pull llama3

  4. Verify it's running:
     curl http://localhost:11434/api/tags
""")

    elif mode == "docker":
        print("""
  Your setup: Running inside a Docker container.

  Option A — Run Ollama on the host and connect via Docker networking:

    1. On the host, start Ollama:
       ollama serve

    2. In your Docker run command, add:
       --add-host=host.docker.internal:host-gateway

    3. Use this URL:
       --ollama-url http://host.docker.internal:11434

  Option B — Run Ollama as a sibling container:

    1. Start Ollama container:
       docker run -d --name ollama -p 11434:11434 ollama/ollama

    2. Pull the model:
       docker exec ollama ollama pull llama3

    3. Use this URL (from within Docker network):
       --ollama-url http://ollama:11434
       Or from host network:
       --ollama-url http://localhost:11434
""")

    elif mode == "wsl":
        host_ip = get_wsl_host_ip()
        print(f"""
  Your setup: Windows Subsystem for Linux (WSL).

  Ollama is typically installed on the Windows host, not inside WSL.

  Option A — Connect to Windows host Ollama:

    1. Install Ollama on Windows: https://ollama.com/download
    2. Start Ollama on Windows (it runs as a service or tray app)
    3. Use the Windows host IP from WSL:
       {"--ollama-url http://" + host_ip + ":11434" if host_ip else "(could not detect host IP)"}

  Option B — Run Ollama natively inside WSL:

    1. Inside WSL, install Ollama:
       curl -fsSL https://ollama.com/install.sh | sh

    2. Start the server:
       ollama serve

    3. Use the default URL:
       --ollama-url http://localhost:11434

  Note: If using Windows Ollama, ensure port 11434 is not blocked by
  Windows Firewall for WSL network access.
""")

    else:
        print(f"""
  Could not determine your runtime mode.

  General steps:
    1. Ensure Ollama is installed and running
    2. Verify the URL is correct: {base_url}
    3. Test manually: curl {base_url}/api/tags
""")


def main():
    parser = argparse.ArgumentParser(
        description="Diagnose Ollama runtime environment for LLM Chess Engine.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  python scripts/check_ollama_env.py
  python scripts/check_ollama_env.py --url http://host.docker.internal:11434
  python scripts/check_ollama_env.py --model llama3:8b
""",
    )
    parser.add_argument("--url", default=os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434"),
                        help="Ollama server URL (default: http://localhost:11434)")
    parser.add_argument("--model", default="llama3",
                        help="Model to check for (default: llama3)")
    parser.add_argument("--json", action="store_true",
                        help="Output results as JSON")

    args = parser.parse_args()

    # ── Detect Mode ──────────────────────────────────────
    mode, mode_details = detect_mode()

    # ── Check Connectivity ───────────────────────────────
    connected, conn_msg = check_connectivity(args.url)

    # ── Check Model ──────────────────────────────────────
    model_found = False
    available_models = []
    model_error = ""
    if connected:
        model_found, available_models, model_error = check_models(args.url, args.model)

    # ── Check Local Process ──────────────────────────────
    process_running = check_ollama_process()

    # ── JSON Output ──────────────────────────────────────
    if args.json:
        result = {
            "mode": mode,
            "mode_details": mode_details,
            "connected": connected,
            "connection_message": conn_msg,
            "model_found": model_found,
            "available_models": available_models,
            "process_running": process_running,
            "url": args.url,
            "requested_model": args.model,
        }
        print(json.dumps(result, indent=2))
        sys.exit(0 if connected and model_found else 1)

    # ── Human Output ─────────────────────────────────────
    print("=" * 60)
    print("  Ollama Environment Diagnostic")
    print("=" * 60)

    # Mode
    print(f"\n  Runtime Mode:     {mode.upper()}")
    for d in mode_details:
        print(f"    • {d}")

    # Process
    print(f"\n  Ollama Process:   {'✓ Running' if process_running else '✗ Not detected'}")

    # Connectivity
    if connected:
        print(f"  Connectivity:     ✓ {conn_msg}")
    else:
        print(f"  Connectivity:     ✗ {conn_msg}")

    # Model
    if connected:
        if model_found:
            print(f"  Model '{args.model}':  ✓ Available")
        else:
            print(f"  Model '{args.model}':  ✗ Not found")
            if available_models:
                print(f"    Available: {', '.join(available_models)}")
            print(f"    Fix: ollama pull {args.model}")

    # ── Overall Status ───────────────────────────────────
    print(f"\n{'─' * 60}")
    if connected and model_found:
        print("  ✅ READY — Ollama is configured and model is available.")
        print(f"\n  You can now run experiments:")
        print(f"    python scripts/run_game.py --temperature 0.2 --seed 42")
        print(f"    bash scripts/run_experiment_matrix.sh")
    elif connected and not model_found:
        print(f"  ⚠️  PARTIAL — Ollama is running but model '{args.model}' is missing.")
        print(f"  Fix: ollama pull {args.model}")
    else:
        print("  ❌ NOT READY — Cannot reach Ollama.")
        print_remediation(mode, connected, args.url)

    print(f"{'─' * 60}")

    sys.exit(0 if connected and model_found else 1)


if __name__ == "__main__":
    main()
