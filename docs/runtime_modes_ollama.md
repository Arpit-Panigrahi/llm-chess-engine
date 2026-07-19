# Ollama Runtime Environments: Local vs Docker vs WSL

This guide provides instructions and troubleshooting steps for configuring, verifying, and routing connections to Ollama across Native Linux, Docker, and Windows Subsystem for Linux (WSL) environments.

## Diagnostics

Before starting development or runs, diagnose your connection using:

```bash
python scripts/check_ollama_env.py
```

This will automatically output the detected mode, connection status, process status, and model availability index.

---

## 1. Native Local Runtime

This is the default setup where Ollama and the chess engine python runtime run on the same native host machine.

- **API Endpoint**: `http://localhost:11434`
- **Default Action**:
  ```bash
  # Check if Ollama is running
  curl http://localhost:11434/api/tags
  ```

### Troubleshooting
- **Connection Refused**: Ollama might not be running. Start it:
  ```bash
  ollama serve
  ```
- **Model Missing**: The engine will fail if `llama3` is not pulled onto the machine:
  ```bash
  ollama pull llama3
  ```

---

## 2. Docker Containers

When running the engine or experiments from inside a Docker container, `localhost` inside the container refers to the container itself, not the host machine running Ollama.

### Co-locating in the same Docker Network
Alternatively, if Ollama is run inside a container:
1. Start Ollama:
   ```bash
   docker run -d --name ollama -p 11434:11434 -v ollama:/root/.ollama ollama/ollama
   ```
2. Pull the model:
   ```bash
   docker exec -it ollama ollama pull llama3
   ```
3. Run the chess engine container in the same network:
   ```bash
   # Use the container name as host in the URL:
   python scripts/run_game.py --ollama-url http://ollama:11434
   ```

### Connecting to Ollama on the Host Machine
If Ollama is running on the host machine and the chess engine is in Docker:
1. Start the container with host loopback mapping (Linux hosts):
   ```bash
   docker run --add-host=host.docker.internal:host-gateway -it my-chess-app
   ```
2. Command the engine using:
   ```bash
   python scripts/run_game.py --ollama-url http://host.docker.internal:11434
   ```

---

## 3. Windows Subsystem for Linux (WSL / WSL2)

In WSL2, the Linux instance runs inside a lightweight utility VM. It has a separate IP address from the Windows Host machine.

### Accessing Ollama Running on Windows Host
Ollama is usually installed as a native Windows application. To access it from WSL2:

1. **Get Windows Host IP**:
   Under WSL2, obtain the ip of the host from `/etc/resolv.conf`:
   ```bash
   cat /etc/resolv.conf | grep nameserver | awk '{print $2}'
   ```
2. **Connect**:
   Pass this IP to the script or environment:
   ```bash
   python scripts/run_game.py --ollama-url http://<WSL_HOST_IP>:11434
   ```

### Accessing WSL Ollama Natively
If you prefer to run Ollama natively inside the WSL Ubuntu/Debian instance:
1. Install inside WSL:
   ```bash
   curl -fsSL https://ollama.com/install.sh | sh
   ```
2. Start serve daemon:
   ```bash
   ollama serve
   ```
3. Run using default localhost.

---

## Network & Firewall Gotchas
- **Windows Firewall**: If accessing Windows Ollama from WSL2, you may need to add an Inbound Rule in Windows Defender Firewall allowing port `11434` for the WSL virtual network interface.
- **Environment variables**: Ollama on Windows can be configured to bind to all interfaces by setting the system environment variable `OLLAMA_HOST=0.0.0.0`. Restart Ollama after configuring.
