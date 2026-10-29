// Decides whether the page in front of the person is a job posting or a job
// application. Riseply stays out of the way on every other page (shops,
// news, search results). Plain DOM code with no extension APIs so it can be
// tested on a normal page.
//
// Strong evidence wins on its own: a known application-system host, or the
// page's own JobPosting data. Everything else needs the page to read like a
// job: weak hints (a /careers/ URL, an "Apply" button) only count when the
// text also talks about responsibilities, qualifications, experience and so
// on. A page that sells things is never treated as a job.
(function () {
  const ATS_HOSTS = [
    "greenhouse.io", "lever.co", "ashbyhq.com", "myworkdayjobs.com",
    "smartrecruiters.com", "jobvite.com", "icims.com", "taleo.net",
    "breezy.hr", "workable.com", "bamboohr.com", "recruitee.com",
  ];
  const JOB_URL_HINTS = ["/jobs/", "/job/", "/careers/", "/career/", "/viewjob", "/positions/", "/vacancy/"];
  // "Apply" alone is also a filter button; these are the wordings that mean a job.
  const APPLY_PATTERN = /^apply\s*(now|for this (job|position|role|opening))?\s*$/i;
  const SHOP_BUTTON = /^(add to (cart|bag|basket)|buy( it)? now|add to wishlist|checkout)$/i;

  // Each pattern counts once, so a page that repeats one word is not a job.
  const JOB_WORDS = [
    /responsibilit/i,
    /qualifications?/i,
    /\brequirements?\b/i,
    /what you(?:'|’)?ll (?:do|bring|need)/i,
    /about (?:the|this) (?:role|job|position|team)/i,
    /\d+\+?\s*(?:years?|yrs)\b[^.]{0,40}\bexperience/i,
    /equal (?:employment )?opportunity/i,
    /\b(?:full|part)[- ]time\b/i,
    /(?:salary|compensation|pay range)/i,
    /\bcover letter\b/i,
    /\b(?:resume|r[eé]sum[eé]|curriculum vitae)\b/i,
    /\bjob (?:description|title|id|type)\b/i,
    /\b(?:apply|applying) (?:for|to) (?:this|the)\b/i,
  ];

  function hasJobPostingData() {
    for (const s of document.querySelectorAll('script[type="application/ld+json"]')) {
      if (/"@type"\s*:\s*(?:\[[^\]]*)?"JobPosting"/.test(s.textContent || "")) return true;
    }
    return false;
  }

  function looksLikeShop() {
    if (document.querySelector('meta[property="og:type"][content="product"], meta[property="og:type"][content="product.item"]')) return true;
    for (const s of document.querySelectorAll('script[type="application/ld+json"]')) {
      if (/"@type"\s*:\s*(?:\[[^\]]*)?"Product"/.test(s.textContent || "")) return true;
    }
    return Array.from(document.querySelectorAll("a, button, input[type=submit]")).some((el) =>
      SHOP_BUTTON.test(((el.textContent || el.value || "")).trim())
    );
  }

  function jobWordCount(text) {
    return JOB_WORDS.reduce((n, re) => n + (re.test(text) ? 1 : 0), 0);
  }

  function inspect() {
    const host = location.hostname.toLowerCase();
    const path = location.pathname.toLowerCase();
    if (ATS_HOSTS.some((h) => host === h || host.endsWith("." + h))) return { job: true, why: "known application site" };
    if (hasJobPostingData()) return { job: true, why: "JobPosting data" };
    if (looksLikeShop()) return { job: false, why: "shop page" };

    const text = (document.body?.innerText || "").slice(0, 60000);
    const words = jobWordCount(text);
    if (JOB_URL_HINTS.some((h) => path.includes(h)) && words >= 2) return { job: true, why: "job URL and " + words + " job phrases" };

    const applyEl = Array.from(document.querySelectorAll("a, button")).find((el) => APPLY_PATTERN.test((el.textContent || "").trim()));
    if (applyEl && text.length > 1500 && words >= 3) return { job: true, why: "Apply button and " + words + " job phrases" };
    return { job: false, why: "not enough job signals (" + words + ")" };
  }

  window.RisePlyDetect = { inspect, isJobPage: () => inspect().job };
})();
