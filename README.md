# Traefik FreeIPA Sync

Automated DNS and certificate management for Docker Swarm services. Automatically syncs Traefik-routed services to FreeIPA DNS with SSL certificates, featuring a built-in web catalog of internal services.

## Features

- **Automatic DNS Management**: Monitors Docker Swarm events and creates/removes DNS records in FreeIPA
- **Certificate Automation**: Requests and manages SSL certificates from FreeIPA
- **Multi-Hostname Support**: Handles services with multiple entrypoints/domain names
- **Web Catalog**: Provides a visual catalog of all internal services
- **Traefik Integration**: Automatically discovers services from Traefik router labels

## How It Works

1. Monitors Docker Swarm service events (create, update, remove)
2. Extracts hostnames from Traefik router labels or explicit `dns.hostname` labels
3. Creates DNS A records in FreeIPA pointing to Traefik load balancer IPs
4. Requests SSL certificates from FreeIPA for each hostname
5. Updates Traefik certificate configuration dynamically
6. Displays all services in a web-based catalog

## Requirements

- Docker Swarm cluster
- Traefik reverse proxy
- FreeIPA server with DNS and CA configured
- Services must have the required label (default: `dns.manage=true`)

## Configuration

Create a `config.yml` file:

```yaml
freeipa:
  server: ipa.example.com
  domain: EXAMPLE.COM
  dns_zone: example.com
  username: admin
  password: your-password

swarm:
  traefik_ips:
    - 10.0.0.10
    - 10.0.0.11
  required_label: dns.manage
  extract_from_traefik: true

certificates:
  enabled: true
  cert_path: /certs/services
  validity_days: 730
  renew_threshold_days: 30

web:
  enabled: true
  port: 8080
  title: "Internal Service Catalog"
  description: "Auto-discovered services"

logging:
  level: INFO
  file: /logs/dns-automation.log
```

## Docker Service Labels

### Automatic Discovery from Traefik

The service automatically discovers hostnames from Traefik router rules:

```yaml
services:
  myapp:
    image: myapp:latest
    labels:
      - "dns.manage=true"
      - "traefik.enable=true"
      - "traefik.http.routers.myapp-web.rule=Host(`web.example.com`)"
      - "traefik.http.routers.myapp-api.rule=Host(`api.example.com`)"
```

Both `web.example.com` and `api.example.com` will get DNS records and certificates.

### Explicit Hostname Label

Alternatively, specify hostname explicitly:

```yaml
labels:
  - "dns.manage=true"
  - "dns.hostname=myservice"
```

## Deployment

### Using Pre-built Images

Images are automatically built and published to Docker Hub on every push to main:

```bash
# Pull the latest image
docker pull <your-dockerhub-username>/traefik-freeipa-sync:latest

# Or use a specific version tag
docker pull <your-dockerhub-username>/traefik-freeipa-sync:v1.0.0
```

### Build the Container Manually

```bash
# For ARM64
docker build -t traefik-freeipa-sync:latest .

# For AMD64 (on ARM Mac)
docker buildx build --platform linux/amd64 -t traefik-freeipa-sync:amd64 .

# Multi-platform build
docker buildx build --platform linux/amd64,linux/arm64 -t traefik-freeipa-sync:latest .
```

### Deploy to Swarm

```bash
docker stack deploy -c docker-compose.yml traefik-freeipa-sync
```

Example `docker-compose.yml`:

```yaml
version: '3.8'

services:
  traefik-freeipa-sync:
    image: traefik-freeipa-sync:latest
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
      - ./config.yml:/config/config.yml:ro
      - ./certs:/certs/services
      - ./logs:/logs
      - traefik-config:/traefik-config
    networks:
      - traefik
    deploy:
      placement:
        constraints:
          - node.role == manager

volumes:
  traefik-config:
    external: true

networks:
  traefik:
    external: true
```

## Web Catalog

Access the service catalog at `http://<host>:8080` to view:

- All auto-discovered services
- Manual services from config
- SSL certificate status
- Service categories

## GitHub Actions CI/CD

The repository includes a GitHub Actions workflow that automatically:
- Builds multi-platform Docker images (AMD64 and ARM64)
- Publishes to Docker Hub on push to `main` branch
- Creates tagged releases when you push version tags (e.g., `v1.0.0`)
- Updates the Docker Hub repository description from README.md

### Setup GitHub Secrets

To enable automatic builds, add these secrets to your GitHub repository:

1. Go to **Settings** → **Secrets and variables** → **Actions**
2. Add the following secrets:
   - `DOCKERHUB_USERNAME`: Your Docker Hub username
   - `DOCKERHUB_TOKEN`: Docker Hub access token (generate at https://hub.docker.com/settings/security)

### Tagging Releases

```bash
# Create and push a version tag
git tag v1.0.0
git push origin v1.0.0

# This will create images tagged as:
# - your-username/traefik-freeipa-sync:1.0.0
# - your-username/traefik-freeipa-sync:1.0
# - your-username/traefik-freeipa-sync:1
# - your-username/traefik-freeipa-sync:latest
```

## Files

- `dns-automation.py` - Main automation script
- `web_catalog.py` - Web interface for service catalog
- `Dockerfile` - Container build definition
- `.github/workflows/docker-publish.yml` - CI/CD workflow for Docker Hub

## License

MIT
