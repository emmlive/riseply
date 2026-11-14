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

  // Subdomains that name a function, not the employer: apply.acme.com is Acme.
  const GENERIC = new Set(["www", "apply", "jobs", "job", "careers", "career", "boards", "board", "recruiting",
    "recruit", "hire", "hiring", "talent", "external", "ext", "work", "workat", "join", "app", "secure"]);

  function hostCompany(host) {
    const labels = String(host || "").toLowerCase().split(".").filter(Boolean);
    const pick = labels.slice(0, -1).find((l) => !GENERIC.has(l) && !/^wd\d+$/.test(l));
    return pick || labels[0] || "";
  }

  function siteName() {
    const og = document.querySelector('meta[property="og:site_name"]')?.content;
    return clean(og || hostCompany(location.hostname), 200);
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

  // ---------- the job description ----------
  // The whole page's text is mostly menus, other jobs in a side list, cookie
  // banners and the application form; the real posting can sit below 6,000
  // characters of that, and the backend only reads the first 6,000. So the
  // posting itself is found: structured data first, then the site's own
  // description box, then the densest block of job-like text, and only then
  // the page with its menus, side lists and forms removed.
  const MAX_DESC = 18000;
  const MIN_DESC = 300;

  function htmlToText(html) {
    const marked = String(html || "")
      .replace(/<\s*br\s*\/?>/gi, "\n").replace(/<\s*li[^>]*>/gi, "\n- ")
      .replace(/<\/(p|div|h[1-6]|ul|ol|tr|section)>/gi, "$&\n");
    const doc = new DOMParser().parseFromString(marked, "text/html"); // inert: no scripts run
    return tidy(doc.body ? doc.body.textContent : "");
  }

  function tidy(t) {
    return String(t || "").replace(/\u00a0/g, " ").replace(/[ \t]+\n/g, "\n").replace(/\n{3,}/g, "\n\n").trim();
  }

  const DESC_SELECTORS = [
    "[data-automation-id='jobPostingDescription']",               // Workday
    "#job-details", ".jobs-description__content", ".jobs-box__html-content", // LinkedIn
    ".show-more-less-html__markup", ".description__text",         // LinkedIn (public pages)
    "#jobDescriptionText", ".jobsearch-JobComponent-description", // Indeed
    "#content .content", "#content",                              // Greenhouse
    ".posting-page .content", "[data-qa='job-description']",      // Lever
    "[itemprop='description']", "#job-description", ".job-description",
    "[class*='job-description']", "[class*='jobDescription']", "[class*='job_description']",
    "[data-testid*='description']",
  ];

  function textOf(el) { return tidy(el.innerText || el.textContent || ""); }

  const JOB_WORDS = /\b(responsibilit\w*|qualification\w*|requirement\w*|experience|skills?|benefits|about (the|this) (role|job|team|position)|what you('ll| will)|you will|you bring|nice to have|preferred|salary|compensation|equal opportunity)\b/gi;

  function jobWordHits(t) {
    return new Set((t.match(JOB_WORDS) || []).map((w) => w.toLowerCase())).size;
  }

  function linkShare(el, len) {
    let linked = 0;
    el.querySelectorAll("a").forEach((a) => { linked += (a.textContent || "").length; });
    return len ? linked / len : 0;
  }

  function fromSelectors() {
    for (const sel of DESC_SELECTORS) {
      let best = "";
      try {
        document.querySelectorAll(sel).forEach((el) => {
          const t = textOf(el);
          if (t.length > best.length && t.length <= MAX_DESC) best = t;
        });
      } catch (e) { continue; }
      if (best.length >= MIN_DESC && jobWordHits(best) >= 2) return best;
    }
    return "";
  }

  // No known box: the block whose text reads most like a posting and least like
  // a menu. A wrapper that holds the whole page is link-heavy and loses.
  function densestBlock() {
    let best = "", bestScore = 0;
    let looked = 0;
    document.querySelectorAll("main, [role='main'], article, section, div").forEach((el) => {
      const raw = (el.textContent || "").length;          // cheap; innerText forces layout
      if (raw < 600 || raw > MAX_DESC * 2 || looked >= 250) return;
      looked++;
      const t = textOf(el);
      if (t.length < 600 || t.length > MAX_DESC) return;
      const hits = jobWordHits(t);
      if (hits < 3) return;
      const score = hits * 100 - linkShare(el, t.length) * 600 + Math.min(t.length, 6000) / 60;
      if (score > bestScore) { bestScore = score; best = t; }
    });
    return best;
  }

  // Last resort: the page, without the parts that are never the posting.
  function pageWithoutChrome() {
    const clone = document.body ? document.body.cloneNode(true) : null;
    if (!clone) return "";
    clone.querySelectorAll("nav, header, footer, aside, form, script, style, noscript, svg, [role='navigation'], [role='banner'], [role='contentinfo'], [aria-hidden='true'], [class*='cookie'], [id*='cookie']")
      .forEach((n) => n.remove());
    return tidy(clone.textContent || "");
  }

  function description() {
    let t = "";
    const jp = jobPostingFromJsonLd();
    if (jp && jp.description) {
      const d = htmlToText(jp.description);
      if (d.length >= MIN_DESC) t = d;
    }
    if (!t) t = fromSelectors();
    if (!t) t = densestBlock();
    if (!t) t = pageWithoutChrome();
    if (t.length < MIN_DESC) t = tidy((document.body && document.body.innerText) || "");
    return t.slice(0, MAX_DESC);
  }

  window.RisePlyJob = { read, hostCompany, description };
})();
