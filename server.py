from mcp.server.fastmcp import FastMCP
import dns.resolver

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


if __name__ == "__main__":
    mcp.run()