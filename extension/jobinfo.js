// Reads the job title, company and location from the page the person is
// viewing. Plain DOM code with no extension APIs so it can be tested on a
// normal page. Order of trust: the page's own structured data (JSON-LD
// JobPosting), then the social-share tags, then the best heading, then the
// page title.
(function () {
  const clean = (s, n) => String(s || "").replace(/\s+/g, " ").trim().slice(0, n);

  function jobPostingFromJsonLd() {
    const nodes = [];
    document.querySelectorAll('script[type="application/ld+json"]').forEach((s) => {
      try { nodes.push(JSON.parse(s.textContent)); } catch (e) { /* skip bad JSON */ }
    });
    const flat = [];
    const walk = (n) => {
      if (!n) return;
      if (Array.isArray(n)) { n.forEach(walk); return; }
      if (typeof n === "object") { flat.push(n); if (n["@graph"]) walk(n["@graph"]); }
    };
    walk(nodes);
    return flat.find((n) => [].concat(n["@type"] || []).includes("JobPosting")) || null;
  }

  function placeText(loc) {
    const l = Array.isArray(loc) ? loc[0] : loc;
    const a = l && l.address;
    if (!a) return "";
    if (typeof a === "string") return a;
    return [a.addressLocality, a.addressRegion, a.addressCountry && (a.addressCountry.name || a.addressCountry)].filter(Boolean).join(", ");
  }

  function siteName() {
    const og = document.querySelector('meta[property="og:site_name"]')?.content;
    return clean(og || location.hostname.replace(/^(www|jobs|careers|boards)\./, "").split(".")[0], 200);
  }

  // The job heading is rarely the first <h1>: logos and site banners are
  // often <h1> too. Take the first heading that is not the site name or a
  // generic "Careers" banner, falling back to the page title.
  function bestHeading(company) {
    const bad = (t) => {
      const x = t.toLowerCase();
      return x.length < 4 || x === company.toLowerCase() || /^(careers?|jobs?|[\w .&-]{1,30} careers?|home|search( results)?)$/.test(x);
    };
    const heads = Array.from(document.querySelectorAll("h1, h2, [role='heading'][aria-level='1']"))
      .filter((h) => h.offsetWidth || h.offsetHeight || h.getClientRects().length);
    for (const h of heads) {
      const t = clean(h.textContent, 300);
      if (!bad(t)) return t;
    }
    return "";
  }

  function read() {
    const jp = jobPostingFromJsonLd();
    const company = clean((jp && jp.hiringOrganization && (jp.hiringOrganization.name || jp.hiringOrganization)) || siteName(), 200);
    let title = clean(jp && jp.title, 300);
    if (!title) {
      const ogt = clean(document.querySelector('meta[property="og:title"]')?.content, 300);
      title = bestHeading(company) || ogt || clean(document.title, 300);
    }
    const location = clean(jp && placeText(jp.jobLocation), 200);
    return { title, company: typeof company === "string" ? company : "", location };
  }

  window.RisePlyJob = { read };
})();
