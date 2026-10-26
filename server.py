from mcp.server.fastmcp import FastMCP
import dns.resolver
import requests

from starlette.responses import HTMLResponse

@mcp.custom_route("/dashboard", methods=["GET"])
async def dashboard(request):
    return HTMLResponse("""
    <!DOCTYPE html>
    <html>
    <head>
      <meta name="viewport"
            content="width=device-width, initial-scale=1">
      <title>Restaurant Health Checker</title>
      <style>
        body {
          font-family: Arial, sans-serif;
          background: #f5f7fb;
          padding: 24px;
        }
        main {
          max-width: 500px;
          margin: 40px auto;
          background: white;
          padding: 24px;
          border-radius: 16px;
        }
        input, button {
          width: 100%;
          padding: 12px;
          margin-top: 12px;
          box-sizing: border-box;
        }
        button {
          background: #2563eb;
          color: white;
          border: none;
          border-radius: 8px;
        }
      </style>
    </head>
    <body>
      <main>
        <h2>Restaurant Health Checker</h2>
        <p>Check your restaurant website's health.</p>
        <input id="domain" placeholder="example.com">
        <button onclick="check()">Check Website</button>
        <pre id="result"></pre>
      </main>
      <script>
        async function check() {
          const domain = document.getElementById("domain").value;
          const result = document.getElementById("result");
          result.textContent = "Checking...";
          try {
            const response = await fetch(
              "/api/check?domain=" + encodeURIComponent(domain)
            );
            const data = await response.json();
            result.textContent = JSON.stringify(data, null, 2);
          } catch (error) {
            result.textContent = "Request failed: " + error.message;
          }
        }
      </script>
    </body>
    </html>
    """)
    
mcp = FastMCP("Restaurant Health Checker")


@mcp.tool()
def check_dns(domain: str) -> dict:
    """Check whether a website domain has DNS A records."""
    domain = domain.strip().lower()

    if "://" in domain or "/" in domain:
        return {
            "error": "Enter a domain like example.com"
        }

    try:
        records = dns.resolver.resolve(domain, "A")

        return {
            "domain": domain,
            "status": "success",
            "ip_addresses": [str(record) for record in records],
        }

    except dns.exception.DNSException as error:
        return {
            "domain": domain,
            "status": "error",
            "message": str(error),
        }


@mcp.tool()
def check_website(url: str) -> dict:
    """Check whether a website is responding."""
    url = url.strip()

    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    try:
        response = requests.get(
            url,
            timeout=10,
            allow_redirects=True,
            headers={"User-Agent": "RestaurantHealthChecker/1.0"},
        )

        return {
            "url": url,
            "status_code": response.status_code,
            "reachable": True,
            "healthy": response.status_code < 400,
            "final_url": response.url,
        }

    except requests.RequestException as error:
        return {
            "url": url,
            "reachable": False,
            "healthy": False,
            "error": str(error),
        }
        
if __name__ == "__main__":
    mcp.run()