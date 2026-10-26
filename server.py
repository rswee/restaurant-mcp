from html.parser import HTMLParser


class SEOParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_title = False
        self.title_parts = []
        self.description = ""
        self.h1_count = 0
        self.image_count = 0
        self.images_missing_alt = 0
        self.canonical = ""
        self.robots = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)

        if tag == "title":
            self.in_title = True

        elif tag == "h1":
            self.h1_count += 1

        elif tag == "meta":
            name = (attrs.get("name") or "").lower()
            content = attrs.get("content") or ""

            if name == "description":
                self.description = content.strip()

            if name in ("robots", "googlebot"):
                self.robots.append(content)

        elif tag == "link":
            rel = (attrs.get("rel") or "").lower().split()
            if "canonical" in rel:
                self.canonical = attrs.get("href") or ""

        elif tag == "img":
            self.image_count += 1
            # Empty alt text can be valid for decorative images.
            if "alt" not in attrs:
                self.images_missing_alt += 1

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False

    def handle_data(self, data):
        if self.in_title:
            self.title_parts.append(data)


@mcp.tool()
def check_seo(domain: str) -> dict:
    """Check basic SEO signals in a public website's homepage HTML."""
    try:
        hostname = validate_domain(domain)
        url = f"https://{hostname}/"

        with requests.Session() as session:
            session.trust_env = False

            with session.get(
                url,
                timeout=(5, 15),
                allow_redirects=False,
                stream=True,
                headers={"User-Agent": "RestaurantHealthChecker/1.0"},
            ) as response:
                status = response.status_code

                if 300 <= status < 400:
                    return {
                        "domain": hostname,
                        "status": "redirect",
                        "status_code": status,
                        "location": response.headers.get("Location"),
                        "message": (
                            "This homepage redirects. Check the destination "
                            "domain separately; redirects are not followed."
                        ),
                    }

                response.raise_for_status()

                content_type = response.headers.get(
                    "Content-Type", ""
                ).lower()

                if not any(t in content_type for t in (
                    "text/html", "application/xhtml+xml"
                )):
                    return {
                        "status": "error",
                        "message": "The homepage did not return HTML.",
                    }

                # Limit the amount of HTML downloaded.
                body = bytearray()
                for chunk in response.iter_content(chunk_size=65536):
                    body.extend(chunk)
                    if len(body) > 2_000_000:
                        raise ValueError("Page exceeds the 2 MB scan limit.")

                encoding = response.encoding or "utf-8"
                html = body.decode(encoding, errors="replace")
                robots_header = response.headers.get("X-Robots-Tag", "")

        parser = SEOParser()
        parser.feed(html)

        title = " ".join(" ".join(parser.title_parts).split())
        directives = " ".join(
            parser.robots + [robots_header]
        ).lower()
        tokens = set(
            directives.replace(",", " ").replace(":", " ").split()
        )
        noindex = bool(tokens & {"noindex", "none"})

        findings = []

        if not title:
            findings.append("Add a descriptive page title.")

        if not parser.description:
            findings.append("Add a meta description.")

        if parser.h1_count == 0:
            findings.append("Add a clear main H1 heading.")

        if not parser.canonical:
            findings.append(
                "No canonical link found; review whether one is needed."
            )

        if parser.images_missing_alt:
            findings.append(
                f"{parser.images_missing_alt} images lack an alt attribute. "
                "Describe informative images; use empty alt for decorative ones."
            )

        if noindex:
            findings.append(
                "A noindex directive was detected. Review it if this "
                "page should appear in search results."
            )

        return {
            "domain": hostname,
            "status": "success",
            "status_code": status,
            "title": title,
            "meta_description": parser.description,
            "h1_count": parser.h1_count,
            "canonical": parser.canonical,
            "images": parser.image_count,
            "images_missing_alt": parser.images_missing_alt,
            "robots_meta": parser.robots,
            "x_robots_tag": robots_header,
            "noindex_detected": noindex,
            "findings": findings,
            "scope": (
                "Homepage source HTML only. JavaScript is not rendered. "
                "This does not verify rankings, Google indexing, robots.txt, "
                "sitemaps, page speed, or the entire website."
            ),
        }

    except Exception as error:
        return {"status": "error", "message": str(error)}


@mcp.custom_route("/api/seo", methods=["GET"])
async def api_seo(request):
    domain = request.query_params.get("domain", "").strip()

    if not domain:
        return JSONResponse(
            {"error": "Please enter a domain."},
            status_code=400,
        )

    result = await asyncio.to_thread(check_seo, domain)
    return JSONResponse(result)
