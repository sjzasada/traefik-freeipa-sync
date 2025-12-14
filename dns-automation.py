#!/usr/bin/env python3
"""
Docker Swarm DNS and Certificate Automation for FreeIPA
Monitors Docker Swarm events and automatically:
- Registers/removes DNS entries
- Requests/manages certificates from FreeIPA
- Updates Traefik certificate configuration
"""

import docker
import json
import logging
import os
import re
import subprocess
import sys
import time
import yaml
import web_catalog
from datetime import datetime, timedelta
from typing import List

# Load configuration
def load_config(config_path='/config/config.yml'):
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)

config = load_config()

# Setup logging
log_level = getattr(logging, config['logging']['level'].upper())
logging.basicConfig(
    level=log_level,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(config['logging']['file']),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# FreeIPA client
class FreeIPAClient:
    def __init__(self, server, domain, username, password):
        self.server = server
        self.domain = domain
        self.username = username
        self.password = password
        self.dns_zone = config['freeipa']['dns_zone']
        self.cert_enabled = config.get('certificates', {}).get('enabled', False)
        self.cert_path = config.get('certificates', {}).get('cert_path', '/certs/services')
        self.validity_days = config.get('certificates', {}).get('validity_days', 730)
        
    def kinit(self):
        """Authenticate to FreeIPA"""
        try:
            cmd = f"echo '{self.password}' | kinit {self.username}@{self.domain.upper()}"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            if result.returncode == 0:
                logger.info("Successfully authenticated to FreeIPA")
                return True
            else:
                logger.error(f"Failed to authenticate: {result.stderr}")
                return False
        except Exception as e:
            logger.error(f"Exception during kinit: {e}")
            return False
    
    def add_dns_record(self, hostname: str, ip_addresses: List[str]) -> bool:
        """Add DNS A record(s) to FreeIPA"""
        try:
            self.kinit()
            
            for ip in ip_addresses:
                cmd = [
                    'ipa', 'dnsrecord-add',
                    self.dns_zone,
                    hostname,
                    '--a-rec', ip
                ]
                
                result = subprocess.run(cmd, capture_output=True, text=True)
                
                if result.returncode == 0:
                    logger.info(f"Added DNS record: {hostname}.{self.dns_zone} -> {ip}")
                elif 'already exists' in result.stderr.lower():
                    logger.warning(f"DNS record already exists: {hostname}.{self.dns_zone} -> {ip}")
                else:
                    logger.error(f"Failed to add DNS record: {result.stderr}")
                    return False
                    
            return True
        except Exception as e:
            logger.error(f"Exception adding DNS record: {e}")
            return False
    
    def remove_dns_record(self, hostname: str, ip_addresses: List[str]) -> bool:
        """Remove DNS A record(s) from FreeIPA"""
        try:
            self.kinit()
            
            for ip in ip_addresses:
                cmd = [
                    'ipa', 'dnsrecord-del',
                    self.dns_zone,
                    hostname,
                    '--a-rec', ip
                ]
                
                result = subprocess.run(cmd, capture_output=True, text=True)
                
                if result.returncode == 0:
                    logger.info(f"Removed DNS record: {hostname}.{self.dns_zone} -> {ip}")
                elif 'not found' in result.stderr.lower():
                    logger.warning(f"DNS record not found: {hostname}.{self.dns_zone} -> {ip}")
                else:
                    logger.error(f"Failed to remove DNS record: {result.stderr}")
                    return False
                    
            return True
        except Exception as e:
            logger.error(f"Exception removing DNS record: {e}")
            return False
    
    def ensure_service_principal(self, hostname: str) -> bool:
        """Ensure host and service principal exist in FreeIPA"""
        try:
            self.kinit()
            fqdn = f"{hostname}.{self.dns_zone}"
            
            # Add host (ignore if exists)
            cmd = ['ipa', 'host-add', fqdn, '--force']
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                logger.info(f"Created host: {fqdn}")
            elif 'already exists' in result.stderr.lower():
                logger.debug(f"Host already exists: {fqdn}")
            else:
                logger.warning(f"Could not create host: {result.stderr}")
            
            # Add service principal (ignore if exists)
            cmd = ['ipa', 'service-add', f'HTTP/{fqdn}']
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                logger.info(f"Created service principal: HTTP/{fqdn}")
                return True
            elif 'already exists' in result.stderr.lower():
                logger.debug(f"Service principal already exists: HTTP/{fqdn}")
                return True
            else:
                logger.error(f"Failed to create service principal: {result.stderr}")
                return False
                
        except Exception as e:
            logger.error(f"Exception ensuring service principal: {e}")
            return False
    
    def request_certificate(self, hostname: str) -> bool:
        """Request certificate from FreeIPA for hostname"""
        if not self.cert_enabled:
            return True
        
        try:
            self.kinit()
            fqdn = f"{hostname}.{self.dns_zone}"
            
            # Ensure service principal exists
            if not self.ensure_service_principal(hostname):
                logger.error(f"Cannot request certificate without service principal for {hostname}")
                return False
            
            # Certificate file paths
            key_file = f"{self.cert_path}/{hostname}.key"
            csr_file = f"/tmp/{hostname}.csr"
            cert_file = f"{self.cert_path}/{hostname}.crt"
            
            # Check if certificate already exists and is valid
            if os.path.exists(cert_file):
                if self.is_certificate_valid(cert_file):
                    logger.info(f"Valid certificate already exists for {hostname}")
                    return True
                else:
                    logger.info(f"Existing certificate for {hostname} is expired or invalid, renewing...")
            
            # Generate private key if doesn't exist
            if not os.path.exists(key_file):
                cmd = ['openssl', 'genrsa', '-out', key_file, '2048']
                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode != 0:
                    logger.error(f"Failed to generate key: {result.stderr}")
                    return False
                os.chmod(key_file, 0o600)
                logger.info(f"Generated private key: {key_file}")
            
            # Generate CSR
            cmd = [
                'openssl', 'req', '-new',
                '-key', key_file,
                '-out', csr_file,
                '-subj', f'/CN={fqdn}/O=ZCloud'
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                logger.error(f"Failed to generate CSR: {result.stderr}")
                return False
            
            # Request certificate from FreeIPA
            cmd = ['ipa', 'cert-request', csr_file, f'--principal=HTTP/{fqdn}']
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                logger.error(f"Failed to request certificate: {result.stderr}")
                return False
            
            # Extract serial number from output
            serial_match = re.search(r'Serial number: (\d+)', result.stdout)
            if not serial_match:
                logger.error(f"Could not find serial number in cert-request output")
                return False
            
            serial = serial_match.group(1)
            logger.info(f"Certificate requested for {hostname}, serial: {serial}")
            
            # Retrieve certificate
            cmd = ['ipa', 'cert-show', serial, f'--out={cert_file}']
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                logger.error(f"Failed to retrieve certificate: {result.stderr}")
                return False
            
            os.chmod(cert_file, 0o644)
            logger.info(f"Retrieved certificate: {cert_file}")
            
            # Clean up CSR
            if os.path.exists(csr_file):
                os.remove(csr_file)
            
            # Update Traefik dynamic configuration
            self.update_traefik_certificates()
            
            return True
            
        except Exception as e:
            logger.error(f"Exception requesting certificate: {e}", exc_info=True)
            return False
    
    def revoke_certificate(self, hostname: str) -> bool:
        """Revoke and remove certificate for hostname"""
        if not self.cert_enabled:
            return True
        
        try:
            cert_file = f"{self.cert_path}/{hostname}.crt"
            key_file = f"{self.cert_path}/{hostname}.key"
            
            # Remove certificate files
            for file in [cert_file, key_file]:
                if os.path.exists(file):
                    os.remove(file)
                    logger.info(f"Removed certificate file: {file}")
            
            # Update Traefik configuration
            self.update_traefik_certificates()
            
            return True
            
        except Exception as e:
            logger.error(f"Exception revoking certificate: {e}")
            return False
    
    def is_certificate_valid(self, cert_file: str) -> bool:
        """Check if certificate is valid and not expiring soon"""
        try:
            # Get expiration date
            cmd = ['openssl', 'x509', '-in', cert_file, '-noout', '-enddate']
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                return False
            
            # Parse date
            date_str = result.stdout.strip().replace('notAfter=', '')
            expiry = datetime.strptime(date_str, '%b %d %H:%M:%S %Y %Z')
            
            # Check if expiring soon
            renew_threshold = config.get('certificates', {}).get('renew_threshold_days', 30)
            threshold = datetime.now() + timedelta(days=renew_threshold)
            
            if expiry < threshold:
                logger.info(f"Certificate expires on {expiry}, renewing...")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error checking certificate validity: {e}")
            return False
    
    def update_traefik_certificates(self):
        """Update Traefik dynamic certificate configuration"""
        try:
            config_file = '/traefik-config/certificates.yml'
            
            # Build certificate list
            certificates = []
            if os.path.exists(self.cert_path):
                for filename in os.listdir(self.cert_path):
                    if filename.endswith('.crt'):
                        hostname = filename[:-4]  # Remove .crt
                        key_file = f"{self.cert_path}/{hostname}.key"
                        cert_file = f"{self.cert_path}/{hostname}.crt"
                        
                        if os.path.exists(key_file):
                            certificates.append({
                                'certFile': cert_file,
                                'keyFile': key_file
                            })
            
            # Build configuration
            traefik_config = {
                'tls': {
                    'certificates': certificates,
                    'options': {
                        'default': {
                            'minVersion': 'VersionTLS12',
                            'sniStrict': False
                        }
                    }
                }
            }
            
            # Write configuration
            with open(config_file, 'w') as f:
                yaml.dump(traefik_config, f, default_flow_style=False)
            
            logger.info(f"Updated Traefik certificates configuration with {len(certificates)} certificates")
            
        except Exception as e:
            logger.error(f"Error updating Traefik configuration: {e}", exc_info=True)

# Extract hostnames from service
def extract_hostnames(service) -> List[str]:
    """Extract all hostnames from service labels"""
    try:
        hostnames = []
        spec = service.attrs.get('Spec', {})
        labels = spec.get('Labels', {})

        # Method 1: Check for explicit dns.hostname label
        if 'dns.hostname' in labels:
            hostname = labels['dns.hostname']
            hostname = hostname.replace(f'.{config["freeipa"]["dns_zone"]}', '')
            hostnames.append(hostname)

        # Method 2: Extract from ALL Traefik router rules
        if config['swarm']['extract_from_traefik']:
            for key, value in labels.items():
                if 'traefik.http.routers' in key and '.rule' in key:
                    match = re.search(r'Host\(`([^`]+)`\)', value)
                    if match:
                        fqdn = match.group(1)
                        if fqdn.endswith(f'.{config["freeipa"]["dns_zone"]}'):
                            hostname = fqdn.replace(f'.{config["freeipa"]["dns_zone"]}', '')
                            # Avoid duplicates
                            if hostname not in hostnames:
                                hostnames.append(hostname)

        return hostnames
    except Exception as e:
        logger.error(f"Error extracting hostnames: {e}")
        return []

# Main monitoring loop
def main():
    logger.info("Starting DNS and Certificate Automation Service")
    logger.info(f"FreeIPA Server: {config['freeipa']['server']}")
    logger.info(f"DNS Zone: {config['freeipa']['dns_zone']}")
    logger.info(f"Traefik IPs: {config['swarm']['traefik_ips']}")
    logger.info(f"Certificate Automation: {'Enabled' if config.get('certificates', {}).get('enabled') else 'Disabled'}")
    

    # ADD THESE LINES:
    # Load manual services and start web server
    web_catalog.load_manual_services(config)
    web_catalog.start_web_server(config)
    # END NEW LINES

    # Initialize clients
    docker_client = docker.DockerClient(base_url='unix://var/run/docker.sock')
    ipa_client = FreeIPAClient(
        server=config['freeipa']['server'],
        domain=config['freeipa']['domain'],
        username=config['freeipa']['username'],
        password=config['freeipa']['password']
    )
    
    # Initial authentication
    if not ipa_client.kinit():
        logger.error("Failed initial FreeIPA authentication. Exiting.")
        sys.exit(1)
    
    # Create certificate directory if needed
    if ipa_client.cert_enabled:
        os.makedirs(ipa_client.cert_path, exist_ok=True)
    
    # Track managed services (service_id -> List[hostname])
    managed_services = {}
    
    # Sync existing services on startup
    logger.info("Syncing existing services...")
    try:
        services = docker_client.services.list()
        for service in services:
            spec = service.attrs.get('Spec', {})
            labels = spec.get('Labels', {})

            if labels.get(config['swarm']['required_label']) == 'true':
                hostnames = extract_hostnames(service)
                if hostnames:
                    logger.info(f"Syncing existing service: {service.name} -> {hostnames}")

                    # Process each hostname
                    for hostname in hostnames:
                        ipa_client.add_dns_record(hostname, config['swarm']['traefik_ips'])
                        has_cert = False
                        if ipa_client.cert_enabled:
                            has_cert = ipa_client.request_certificate(hostname)

                        web_catalog.update_service_registry(hostname, service.name, config['freeipa']['dns_zone'], True, has_cert)

                    managed_services[service.id] = hostnames
    except Exception as e:
        logger.error(f"Error during initial sync: {e}")
    
    logger.info("Starting event monitoring...")
    
    # Monitor events
    last_kinit = time.time()
    kinit_interval = 3600
    
    for event in docker_client.events(decode=True, filters={'type': 'service'}):
        try:
            # Periodic re-authentication
            if time.time() - last_kinit > kinit_interval:
                ipa_client.kinit()
                last_kinit = time.time()
            
            action = event.get('Action')
            service_id = event.get('Actor', {}).get('ID')
            
            if not service_id:
                continue
            
            logger.debug(f"Service event: {action} for {service_id}")
            
            # Handle removal
            if action == 'remove':
                if service_id in managed_services:
                    hostnames = managed_services[service_id]
                    logger.info(f"Service removed: {service_id[:12]}, cleaning up {hostnames}")

                    # Clean up each hostname
                    for hostname in hostnames:
                        ipa_client.remove_dns_record(hostname, config['swarm']['traefik_ips'])
                        ipa_client.revoke_certificate(hostname)
                        web_catalog.remove_from_registry(hostname)

                    del managed_services[service_id]
                continue
            
            # For create/update
            try:
                service = docker_client.services.get(service_id)
            except docker.errors.NotFound:
                continue

            service_name = service.name
            spec = service.attrs.get('Spec', {})
            labels = spec.get('Labels', {})

            if not labels.get(config['swarm']['required_label']) == 'true':
                continue

            hostnames = extract_hostnames(service)
            if not hostnames:
                continue

            traefik_ips = config['swarm']['traefik_ips']

            if action in ['create', 'update']:
                logger.info(f"Processing service {service_name}: {hostnames}")

                # Process each hostname
                for hostname in hostnames:
                    ipa_client.add_dns_record(hostname, traefik_ips)
                    has_cert = False
                    if ipa_client.cert_enabled:
                        has_cert = ipa_client.request_certificate(hostname)

                    web_catalog.update_service_registry(hostname, service_name, config['freeipa']['dns_zone'], True, has_cert)

                managed_services[service_id] = hostnames
                
        except Exception as e:
            logger.error(f"Error processing event: {e}", exc_info=True)

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Shutting down gracefully...")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
