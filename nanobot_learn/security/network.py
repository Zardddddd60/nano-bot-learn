"""Network security utilities for SSRF protection."""

from __future__ import annotations

import ipaddress
import socket
import re
from urllib.parse import urlparse

_BLOCKED_NETWORKS = [
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]

_allowed_networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []

# Classless Inter-Domain Routing: 无类别域间路由
# 一种表示 IP 网段的写法，表示一个网段
# 192.168.1.0/24
def configure_ssrf_whitelist(cidrs: list[str]):
  """Allow specific CIDR ranges to bypass SSRF blocking (e.g. Tailscale's 100.64.0.0/10)."""
  global _allowed_networks
  nets = []
  for cidr in cidrs:
    try:
      # 把字符串类型转成网段，后边直接判断一个ip在不在网段中
      nets.append(ipaddress.ip_network(cidr, strict=False))
    except ValueError:
      # 不符合就算了
      pass
  _allowed_networks = nets

# IPv4Address是具体的ip地址，IPv4Network是一个网段
def _is_private(addr: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
  if _allowed_networks and any(addr in net for net in _allowed_networks):
    return False
  return any(addr in net for net in _BLOCKED_NETWORKS)

def validate_url_target(url: str) -> tuple[bool, str]:
  """Validate a URL is safe to fetch: scheme, hostname, and resolved IPs.

  Returns (ok, error_message).  When ok is True, error_message is empty.
  """

  try:
    p = urlparse(url)
  except Exception as e:
    return False, str(e)
  
  if p.scheme not in ("http", "https"):
    return False, f"Only http/https allowed, got '{p.scheme or 'None'}'"
  
  if not p.netloc:
    return False, "Missing domain"
  
  hostname = p.hostname
  if not hostname:
    return False, "Missing hostname"
  
  try:
    # dns/地址解析函数：把域名解析成ip
    # AF_UNSPEC: IPv4/v6都可以
    # SOCK_STREAM: 只要 TCP 类型的地址结果
    infos = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
  except socket.gaierror:
    return False, f"Cannot resolve hostname: {hostname}"
  
  for info in infos:
    try:
      addr = ipaddress.ip_address(info[4][0])
    except ValueError:
      continue
    if _is_private(addr):
      return False, f"Blocked: {hostname} resolves to private/internal address {addr}"
  
  return True, ""

def validate_resolved_url(url: str) -> tuple[bool, str]:
  """Validate an already-fetched URL (e.g. after redirect). Only checks the IP, skips DNS."""
  try:
    p = urlparse(url)
  except Exception:
    return True, ""

  hostname = p.hostname
  if not hostname:
    return True, ""

  try:
    addr = ipaddress.ip_address(hostname)
    if _is_private(addr):
      return False, f"Redirect target is a private address: {addr}"
  except ValueError:
    # hostname is a domain name, resolve it
    try:
      infos = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
    except socket.gaierror:
      return True, ""
    for info in infos:
      try:
        addr = ipaddress.ip_address(info[4][0])
      except ValueError:
        continue
      if _is_private(addr):
        return False, f"Redirect target {hostname} resolves to private address {addr}"

  return True, ""

_URL_RE = re.compile(r"https?://[^\s\"'`;|<>]+", re.IGNORECASE)

def contains_internal_url(command: str) -> bool:
  """Return True if the command string contains a URL targeting an internal/private address."""
  for m in _URL_RE.finditer(command):
    url = m.group(0)
    ok, _ = validate_url_target(url)
    if not ok:
      return True
  return False
