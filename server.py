
import asyncio
import ipaddress
import os
import socket
from urllib.parse import urlsplit

import dns.resolver
import requests
from mcp.server.fastmcp import FastMCP
from starlette.responses import HTMLResponse, JSONResponse

PORT = int(os.environ.get("PORT", "8000"))

mcp = FastMCP(
    "Restaurant Health Checker",
    host="0.0.0.0",
    port=PORT,
    stateless_http=True,
    json_response=True,
)


def validate_domain(value: str) -> str:
    """Accept only public website hostnames."""
    value = value.strip()

    if not value:
        raise ValueError("Please enter a website domain.")

    if "://" not in value:
        value = "https://" + value

    parsed = urlsplit(value)

    if parsed.scheme != "https":
        raise ValueError("Only HTTPS websites are supported.")

    if parsed.username or parsed.password:
        raise ValueError("URLs with credentials are not allowed.")

    if parsed.port not in (None, 443):
        raise ValueError("Custom ports are not allowed.")

    hostname = (parsed.hostname or "").lower().rstrip(".")

    if not hostname or "." not in hostname:
        raise ValueError("Enter a public domain such as example.com.")

    if hostname.endswith((".local", ".internal", ".localhost")):
        raise ValueError("Internal domains are not allowed.")

    try:
        ipaddress.ip_address(hostname)
        raise ValueError("Enter a domain name, not an IP address.")
    except ValueError as exc:
        if str(exc).startswith("Enter a domain name"):
            raise

    try:
        addresses = socket.getaddrinfo(
            hostname, 443, type=socket.SOCK_STREAM
        )
    except socket.gaierror:
        raise ValueError("Domain could not be resolved.")

    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if not ip.is_global:
            raise ValueError("Private or reserved addresses are blocked.")

    return hostname


@mcp.tool()
def check_dns(domain: str) -> dict:
    """Check DNS A records for a public restaurant website."""
    try:
        hostname = validate_domain(domain)
        records = dns.resolver.resolve(hostname, "A")

        return {
            "domain": hostname,
            "status": "success",
            "ip_addresses": [str(record) for record in records],
        }

    except Exception as error:
        return {
            "status": "error",
            "message": str(error),
        }


@mcp.tool()
def check_website(url: str) -> dict:
    """Check HTTPS availability for a public website."""
    try:
        hostname = validate_domain(url)

        # Redirects are disabled to avoid following requests
        # to unvalidated destinations.
        session = requests.Session()
        session.trust_env = False

        try:
            response = session.get(
                "https://" + hostname + "/",
                timeout=10,
                allow_redirects=False,
                stream=True,
                headers={
                    "User-Agent": "RestaurantHealthChecker/1.0"
                },
            )

            try:
                status = response.status_code
            finally:
                response.close()
        finally:
            session.close()

        return {
            "domain": hostname,
            "reachable": True,
            "status_code": status,
            "healthy": 200 <= status < 400,
            "redirect": 300 <= status < 400,
        }

    except Exception as error:
        return {
            "reachable": False,
            "healthy": False,
            "error": str(error),
        }


@mcp.custom_route("/", methods=["GET"])
async def health(request):
    return JSONResponse({
        "status": "ok",
        "server": "Restaurant Health Checker",
        "mcp_endpoint": "/mcp",
        "dashboard": "/dashboard",
        "tools": ["check_dns", "check_website"],
    })


@mcp.custom_route("/api/check", methods=["GET"])
async def api_check(request):
    domain = request.query_params.get("domain", "").strip()

    if not domain:
        return JSONResponse(
            {"error": "Please enter a domain."},
            status_code=400,
        )

    try:
        hostname = validate_domain(domain)
    except ValueError as error:
        return JSONResponse(
            {"error": str(error)},
            status_code=400,
        )

    dns_result, website_result = await asyncio.gather(
        asyncio.to_thread(check_dns, hostname),
        asyncio.to_thread(check_website, hostname),
    )

    return JSONResponse({
        "domain": hostname,
        "dns": dns_result,
        "website": website_result,
    })


@mcp.custom_route("/dashboard", methods=["GET"])
async def dashboard(request):
    return HTMLResponse("""
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport"
        content="width=device-width, initial-scale=1">
  <title>Restaurant Health Checker</title>
  <style>
    * { box-sizing: border-box; }
    body {
      margin: 0;
      padding: 24px 16px;
      background: #f3f6fc;
      font-family: system-ui, Arial, sans-serif;
      color: #17233b;
    }
    main {
      max-width: 580px;
      margin: 35px auto;
      background: white;
      padding: 28px;
      border-radius: 20px;
      box-shadow: 0 8px 30px #17233b12;
    }
    h1 { font-size: 26px; margin-bottom: 8px; }
    p { color: #667085; line-height: 1.5; }
    input, button {
      width: 100%;
      padding: 15px;
      border-radius: 10px;
      font-size: 16px;
    }
    input {
      border: 1px solid #cbd5e1;
      margin-top: 14px;
    }
    button {
      margin-top: 12px;
      background: #2563eb;
      color: white;
      border: none;
      font-weight: 600;
      cursor: pointer;
    }
    button:disabled { opacity: 0.6; }
    .result {
      margin-top: 22px;
      padding: 16px;
      background: #f8fafc;
      border-radius: 12px;
      overflow-wrap: anywhere;
    }
    .good { color: #16803c; }
    .bad { color: #c2410c; }
    pre {
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      font-size: 13px;
    }
    small { color: #667085; }
  </style>
</head>
<body>
  <main>
    <h1>🍕 Restaurant Health Checker</h1>
    <p>Check your restaurant website's DNS and availability.</p>

    <form id="checkForm">
      <input
        id="domain"
        placeholder="example.com"
        value="example.com"
        required
      >
      <button id="checkButton" type="submit">
        Check Website
      </button>
    </form>

    <div class="result" id="result" aria-live="polite">
      Enter a public website domain to get started.
    </div>

    <p><small>MCP endpoint: /mcp</small></p>
  </main>

  <script>
    const form = document.getElementById("checkForm");
    const button = document.getElementById("checkButton");
    const result = document.getElementById("result");

    form.addEventListener("submit", async (event) => {
      event.preventDefault();

      const domain = document.getElementById("domain").value.trim();
      button.disabled = true;
      result.textContent = "Checking website...";

      try {
        const response = await fetch(
          "/api/check?domain=" + encodeURIComponent(domain)
        );

        const data = await response.json();

        if (!response.ok) {
          result.textContent = data.error || "Check failed.";
          return;
        }

        const dns = data.dns;
        const web = data.website;

        result.replaceChildren();

        const heading = document.createElement("h3");
        heading.textContent = data.domain;
        result.appendChild(heading);

        const dnsLine = document.createElement("p");
        dnsLine.textContent = "DNS: " + (
          dns.status === "success" ? "Working" : "Error"
        );
        dnsLine.className =
          dns.status === "success" ? "good" : "bad";
        result.appendChild(dnsLine);

        const webLine = document.createElement("p");
        webLine.textContent = "Website: " + (
          web.healthy ? "Healthy" : "Needs attention"
        );
        webLine.className = web.healthy ? "good" : "bad";
        result.appendChild(webLine);

        const details = document.createElement("pre");
        details.textContent = JSON.stringify(data, null, 2);
        result.appendChild(details);

      } catch (error) {
        result.textContent = "Request failed: " + error.message;
      } finally {
        button.disabled = false;
      }
    });
  </script>
</body>
</html>
""")


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
