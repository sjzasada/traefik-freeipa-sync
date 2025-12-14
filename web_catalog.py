#!/usr/bin/env python3
"""
Web-based Service Catalog for DNS Automation
Displays auto-discovered and manual services
"""

import json
import logging
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from threading import Thread

logger = logging.getLogger(__name__)

# Service registry - shared with main script
service_registry = {}

# HTML Template
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
        }}
        header {{
            text-align: center;
            color: white;
            margin-bottom: 40px;
        }}
        h1 {{
            font-size: 2.5em;
            margin-bottom: 10px;
        }}
        .subtitle {{
            font-size: 1.1em;
            opacity: 0.9;
        }}
        .stats {{
            display: flex;
            gap: 20px;
            justify-content: center;
            margin-bottom: 40px;
            flex-wrap: wrap;
        }}
        .stat-card {{
            background: rgba(255, 255, 255, 0.95);
            padding: 20px 30px;
            border-radius: 10px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        }}
        .stat-number {{
            font-size: 2em;
            font-weight: bold;
            color: #667eea;
        }}
        .stat-label {{
            color: #666;
            margin-top: 5px;
        }}
        .category {{
            margin-bottom: 30px;
        }}
        .category-header {{
            background: rgba(255, 255, 255, 0.95);
            padding: 15px 20px;
            border-radius: 10px 10px 0 0;
            font-size: 1.3em;
            font-weight: bold;
            color: #333;
        }}
        .services {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
            gap: 15px;
            padding: 15px;
            background: rgba(255, 255, 255, 0.9);
            border-radius: 0 0 10px 10px;
        }}
        .service-card {{
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
            transition: transform 0.2s, box-shadow 0.2s;
            text-decoration: none;
            color: inherit;
            display: block;
        }}
        .service-card:hover {{
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
        }}
        .service-name {{
            font-size: 1.2em;
            font-weight: bold;
            color: #667eea;
            margin-bottom: 8px;
        }}
        .service-url {{
            color: #666;
            font-size: 0.9em;
            margin-bottom: 8px;
            word-break: break-all;
        }}
        .service-description {{
            color: #888;
            font-size: 0.9em;
            line-height: 1.4;
        }}
        .badge {{
            display: inline-block;
            padding: 4px 10px;
            border-radius: 12px;
            font-size: 0.75em;
            font-weight: bold;
            margin-top: 10px;
        }}
        .badge-auto {{
            background: #e3f2fd;
            color: #1976d2;
        }}
        .badge-manual {{
            background: #f3e5f5;
            color: #7b1fa2;
        }}
        .badge-cert {{
            background: #e8f5e9;
            color: #388e3c;
            margin-left: 5px;
        }}
        footer {{
            text-align: center;
            color: rgba(255, 255, 255, 0.8);
            margin-top: 40px;
            padding: 20px;
        }}
        .refresh-info {{
            background: rgba(255, 255, 255, 0.1);
            padding: 10px;
            border-radius: 5px;
            margin-top: 10px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🚀 {title}</h1>
            <p class="subtitle">{description}</p>
        </header>
        
        <div class="stats">
            <div class="stat-card">
                <div class="stat-number">{total_services}</div>
                <div class="stat-label">Total Services</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{auto_services}</div>
                <div class="stat-label">Auto-discovered</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{manual_services}</div>
                <div class="stat-label">Manual</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{cert_services}</div>
                <div class="stat-label">With Certificates</div>
            </div>
        </div>
        
        {categories_html}
        
        <footer>
            <div class="refresh-info">
                Last updated: {last_updated}<br>
                Auto-refresh: Services are discovered in real-time
            </div>
            <p style="margin-top: 20px;">
                Powered by Docker Swarm DNS Automation
            </p>
        </footer>
    </div>
</body>
</html>
"""

class ServiceCatalogHandler(BaseHTTPRequestHandler):
    """HTTP request handler for service catalog"""
    
    def log_message(self, format, *args):
        """Override to use our logger"""
        logger.debug(f"Web request: {format % args}")
    
    def do_GET(self):
        """Handle GET requests"""
        if self.path == '/' or self.path == '/index.html':
            self.send_catalog()
        elif self.path == '/api/services':
            self.send_json_api()
        elif self.path == '/health':
            self.send_health()
        else:
            self.send_error(404, "Not Found")
    
    def send_catalog(self):
        """Send HTML catalog page"""
        try:
            # Organize services by category
            categories = {}
            auto_count = 0
            cert_count = 0
            
            for service_id, service in service_registry.items():
                category = service.get('category', 'Uncategorized')
                if category not in categories:
                    categories[category] = []
                categories[category].append(service)
                
                if service.get('auto_discovered'):
                    auto_count += 1
                if service.get('has_certificate'):
                    cert_count += 1
            
            # Generate category HTML
            categories_html = ""
            for category in sorted(categories.keys()):
                services = sorted(categories[category], key=lambda x: x['name'])
                
                categories_html += f'<div class="category">'
                categories_html += f'<div class="category-header">{category}</div>'
                categories_html += f'<div class="services">'
                
                for service in services:
                    badge_type = "badge-auto" if service.get('auto_discovered') else "badge-manual"
                    badge_text = "Auto" if service.get('auto_discovered') else "Manual"
                    cert_badge = '<span class="badge badge-cert">🔒 SSL</span>' if service.get('has_certificate') else ''
                    
                    categories_html += f'''
                    <a href="{service['url']}" class="service-card" target="_blank">
                        <div class="service-name">{service['name']}</div>
                        <div class="service-url">{service['url']}</div>
                        <div class="service-description">{service.get('description', '')}</div>
                        <div>
                            <span class="badge {badge_type}">{badge_text}</span>
                            {cert_badge}
                        </div>
                    </a>
                    '''
                
                categories_html += '</div></div>'
            
            # Get config from parent module
            from __main__ import config
            
            # Fill template
            html = HTML_TEMPLATE.format(
                title=config.get('web', {}).get('title', 'Service Catalog'),
                description=config.get('web', {}).get('description', ''),
                total_services=len(service_registry),
                auto_services=auto_count,
                manual_services=len(service_registry) - auto_count,
                cert_services=cert_count,
                categories_html=categories_html,
                last_updated=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            )
            
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Cache-Control', 'no-cache')
            self.end_headers()
            self.wfile.write(html.encode('utf-8'))
            
        except Exception as e:
            logger.error(f"Error generating catalog: {e}", exc_info=True)
            self.send_error(500, str(e))
    
    def send_json_api(self):
        """Send JSON API response"""
        try:
            data = {
                'services': list(service_registry.values()),
                'total': len(service_registry),
                'timestamp': datetime.now().isoformat()
            }
            
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Cache-Control', 'no-cache')
            self.end_headers()
            self.wfile.write(json.dumps(data, indent=2).encode('utf-8'))
            
        except Exception as e:
            logger.error(f"Error generating JSON: {e}", exc_info=True)
            self.send_error(500, str(e))
    
    def send_health(self):
        """Send health check response"""
        self.send_response(200)
        self.send_header('Content-Type', 'text/plain')
        self.end_headers()
        self.wfile.write(b'OK')

def start_web_server(config):
    """Start web server in separate thread"""
    if not config.get('web', {}).get('enabled', False):
        logger.info("Web interface disabled")
        return
    
    port = config.get('web', {}).get('port', 8080)
    
    try:
        server = HTTPServer(('0.0.0.0', port), ServiceCatalogHandler)
        logger.info(f"Starting web server on port {port}")
        
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        
        logger.info(f"Web catalog available at http://0.0.0.0:{port}")
        
    except Exception as e:
        logger.error(f"Failed to start web server: {e}")

def update_service_registry(hostname: str, service_name: str, dns_zone: str,
                           auto_discovered: bool = True, has_certificate: bool = False,
                           description: str = ""):
    """Update the service registry"""
    url = f"https://{hostname}.{dns_zone}"

    # Determine category from service name
    category = "Applications"
    if any(x in service_name.lower() for x in ['traefik', 'portainer', 'prometheus', 'grafana', 'dns', 'catalog']):
        category = "Infrastructure"
    elif any(x in service_name.lower() for x in ['monitor', 'cadvisor', 'node-exporter', 'alertmanager']):
        category = "Monitoring"

    # Use hostname as key to allow multiple entries per service
    service_registry[hostname] = {
        'id': hostname,
        'service_name': service_name,
        'name': service_name.replace('_', ' ').replace('-', ' ').title(),
        'hostname': hostname,
        'url': url,
        'description': description,
        'category': category,
        'auto_discovered': auto_discovered,
        'has_certificate': has_certificate,
        'last_updated': datetime.now().isoformat()
    }

    logger.debug(f"Registry updated: {hostname} -> {url}")

def remove_from_registry(hostname: str):
    """Remove service from registry by hostname"""
    if hostname in service_registry:
        del service_registry[hostname]
        logger.debug(f"Registry removed: {hostname}")

def load_manual_services(config):
    """Load manual services from config"""
    manual_services = config.get('manual_services', [])
    
    for service in manual_services:
        service_id = service['name'].lower().replace(' ', '-')
        service_registry[service_id] = {
            'id': service_id,
            'name': service['name'],
            'hostname': '',
            'url': service['url'],
            'description': service.get('description', ''),
            'category': service.get('category', 'Other'),
            'auto_discovered': False,
            'has_certificate': service['url'].startswith('https://'),
            'last_updated': datetime.now().isoformat()
        }
    
    logger.info(f"Loaded {len(manual_services)} manual services into catalog")
