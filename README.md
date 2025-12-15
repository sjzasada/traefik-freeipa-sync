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
  # Only process services with this label
  required_label: "traefik.enable"
  # Label that contains the hostname to register
  hostname_label: "dns.hostname"
  # Alternative: extract from Traefik router rule
  extract_from_traefik: true

certificates:
  # Enable certificate automation
  enabled: true
  # Certificate storage path (will be mounted to Traefik)
  cert_path: /certs/services
  # Certificate validity in days
  validity_days: 730
  # Auto-renew when certificate expires in X days
  renew_threshold_days: 30


web:
  enabled: true
  port: 8080
  title: "Internal Service Catalog"
  description: "Auto-discovered services"

logging:
  level: INFO
  file: /logs/dns-automation.log

# Manual services (not auto-discovered)
manual_services:
  - name: "FreeIPA"
    url: "https://ipa.example.com
    description: "Identity Management & Certificate Authority"
    category: "Infrastructure"

```

## Docker Service Labels

### Automatic Discovery from Traefik

The service automatically discovers hostnames from Traefik router rules:

```yaml
services:
  myapp:
    image: myapp:latest
    labels:
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
      - ./certs/freeipa-ca.crt:/etc/pki/ca-trust/source/anchors/freeipa-ca.crt:ro #your freeipa CA cert
      - ./traefik-config:/traefik-config
    networks:
      - traefik
    deploy:
      placement:
        constraints:
          - node.role == manager
      #Expose the catalog service through Traefik
      labels:
        - "traefik.enable=true"
        - "traefik.swarm.network=traefik"
        - "traefik.http.routers.catalog.rule=Host(`catalog.example.com`)"
        - "traefik.http.routers.catalog.entrypoints=websecure"
        - "traefik.http.routers.catalog.tls=true"
        - "traefik.http.services.catalog.loadbalancer.server.port=8080"

volumes:
  traefik-config:
    external: true

networks:
  traefik:
    external: true
```

## Web Catalog

Access the service catalog at `https://catalog.example.com` or  `http://<host>:8080` to view:

- All auto-discovered services
- Manual services from config
- SSL certificate status
- Service categories

## Files

- `dns-automation.py` - Main automation script
- `web_catalog.py` - Web interface for service catalog
- `Dockerfile` - Container build definition
- `.github/workflows/docker-publish.yml` - CI/CD workflow for Docker Hub

## License

MIT
