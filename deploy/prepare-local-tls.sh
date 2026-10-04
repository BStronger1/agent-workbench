#!/usr/bin/env bash
set -euo pipefail
APP_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
ip="${1:?Usage: bash deploy/prepare-local-tls.sh PRIVATE_IPV4}"
python3 -c 'import ipaddress,sys; a=ipaddress.IPv4Address(sys.argv[1]); assert a.is_private and not a.is_loopback and not a.is_unspecified, "Use a private LAN IPv4 address"' "$ip"
umask 077
mkdir -p "$APP_DIR/tls"
chmod 700 "$APP_DIR/tls"
cd "$APP_DIR/tls"
if [[ -f ip && "$(cat ip)" != "$ip" ]]; then
  echo 'This CA is bound to a different address. Keep the existing certificates and use a separate TLS directory.' >&2
  exit 1
fi
if [[ ! -f ca.key && ! -f ca.crt ]]; then
  cat > ca.cnf <<EOF
[req]
prompt = no
distinguished_name = dn
x509_extensions = ca
[dn]
CN = Agent Workbench Private CA
O = BStronger1
[ca]
basicConstraints = critical,CA:true,pathlen:0
keyUsage = critical,keyCertSign,cRLSign
subjectKeyIdentifier = hash
authorityKeyIdentifier = keyid:always
nameConstraints = critical,permitted;IP:$ip/255.255.255.255,permitted;DNS:workbench.invalid
EOF
  openssl req -x509 -newkey rsa:3072 -nodes -sha256 -days 1825 -config ca.cnf -keyout ca.key -out ca.crt 2>certificate-generation.log
  printf '%s\n' "$ip" > ip
fi
[[ -f ca.key && -f ca.crt && -f ip ]] || { echo 'Incomplete CA state; restore the TLS backup before continuing.' >&2; exit 1; }
openssl x509 -checkend 15552000 -noout -in ca.crt >/dev/null || { echo 'CA expires too soon; renew and re-enroll client trust before issuing a certificate.' >&2; exit 1; }
cat > server.cnf <<EOF
[req]
prompt = no
distinguished_name = dn
[dn]
CN = workbench.invalid
O = BStronger1
[server]
basicConstraints = critical,CA:false
keyUsage = critical,digitalSignature,keyEncipherment
extendedKeyUsage = serverAuth
subjectAltName = IP:$ip
subjectKeyIdentifier = hash
authorityKeyIdentifier = keyid,issuer
EOF
openssl req -new -newkey rsa:3072 -nodes -sha256 -config server.cnf -keyout server.key.next -out server.csr 2>>certificate-generation.log
openssl x509 -req -in server.csr -CA ca.crt -CAkey ca.key -set_serial "0x$(openssl rand -hex 16)" -days 180 -sha256 -extfile server.cnf -extensions server -out server.crt.next 2>>certificate-generation.log
openssl verify -CAfile ca.crt -verify_ip "$ip" -purpose sslserver server.crt.next
if [[ ! -f store-password ]]; then openssl rand -hex 32 > store-password; fi
openssl pkcs12 -export -name workbench -inkey server.key.next -in server.crt.next -certfile ca.crt -out server.p12.next -passout file:store-password
mv server.key.next server.key
mv server.crt.next server.crt
mv server.p12.next server.p12
cat > server.properties <<EOF
server.ssl.enabled=true
server.ssl.key-store=file:$APP_DIR/tls/server.p12
server.ssl.key-store-type=PKCS12
server.ssl.key-store-password=$(cat store-password)
server.ssl.key-alias=workbench
server.ssl.enabled-protocols=TLSv1.2,TLSv1.3
EOF
chmod 600 ./*
openssl x509 -in ca.crt -noout -sha256 -fingerprint
openssl x509 -in server.crt -noout -dates
echo 'Certificates prepared. Set WORKBENCH_TLS=true in .env, then restart. Distribute ONLY ca.crt to clients.'
