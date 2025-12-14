#!/bin/bash
set -e

echo "Configuring FreeIPA client..."

# Read config
IPA_SERVER=$(grep 'server:' /config/config.yml | awk '{print $2}')
IPA_DOMAIN=$(grep 'domain:' /config/config.yml | awk '{print $2}')

# Configure /etc/hosts if needed
if ! grep -q "$IPA_SERVER" /etc/hosts; then
    # Try to resolve IPA server
    IPA_IP=$(getent hosts $IPA_SERVER | awk '{print $1}')
    if [ -n "$IPA_IP" ]; then
        echo "$IPA_IP $IPA_SERVER" >> /etc/hosts
    fi
fi

# Copy FreeIPA CA certificate to expected location
mkdir -p /etc/ipa
if [ -f /etc/pki/ca-trust/source/anchors/freeipa-ca.crt ]; then
    cp /etc/pki/ca-trust/source/anchors/freeipa-ca.crt /etc/ipa/ca.crt
    echo "Copied FreeIPA CA certificate to /etc/ipa/ca.crt"
fi

# Update CA trust
if [ -f /etc/pki/ca-trust/source/anchors/freeipa-ca.crt ]; then
    update-ca-certificates 2>/dev/null || true
fi

# Configure krb5.conf
cat > /etc/krb5.conf <<EOF
[libdefaults]
  default_realm = ${IPA_DOMAIN^^}
  dns_lookup_realm = false
  dns_lookup_kdc = true
  rdns = false
  ticket_lifetime = 24h
  forwardable = true
  udp_preference_limit = 0

[realms]
  ${IPA_DOMAIN^^} = {
    kdc = $IPA_SERVER
    admin_server = $IPA_SERVER
  }

[domain_realm]
  .$IPA_DOMAIN = ${IPA_DOMAIN^^}
  $IPA_DOMAIN = ${IPA_DOMAIN^^}
EOF

# Create minimal IPA client config
cat > /etc/ipa/default.conf <<EOF
[global]
basedn = dc=$(echo $IPA_DOMAIN | sed 's/\./,dc=/g')
realm = ${IPA_DOMAIN^^}
domain = $IPA_DOMAIN
server = $IPA_SERVER
xmlrpc_uri = https://$IPA_SERVER/ipa/xml
enable_ra = True
EOF

echo "FreeIPA client configured"
echo "Starting DNS automation service..."

# Run the Python script
exec python3 -u /app/dns-automation.py

