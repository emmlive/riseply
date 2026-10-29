// Fills the parts of an application that come from the person's Riseply
// "Autofill profile": work history, education, standard answers, optional
// self-identification answers, and their saved answers to common questions.
//
// Rules this file never breaks:
//  - It only writes a value the person chose or wrote themselves.
//  - A blank profile answer means "leave the question alone".
//  - It never overwrites a field that already has a value or a selection.
//  - It never clicks "Add", "Next" or "Submit". For a second job or school
//    the person adds the block themselves and presses Autofill again.
//  - It never guesses between answer choices: no clear match, no fill.
//
// Plain DOM code with no extension APIs, so it can be tested on a normal page.
(function () {
  const RF = {};

  // ---------- reading the page ----------

  function visible(el) {
    return !!(el && (el.offsetWidth || el.offsetHeight || el.getClientRects().length));
  }

  function norm(s) {
    return String(s || "").replace(/\s+/g, " ").trim().toLowerCase();
  }

  function labelText(el) {
    const bits = [];
    if (el.id) {
      const l = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
      if (l) bits.push(l.textContent);
    }
    const wrap = el.closest("label");
    if (wrap) bits.push(wrap.textContent);
    const by = el.getAttribute("aria-labelledby");
    if (by) by.split(/\s+/).forEach((id) => { const n = document.getElementById(id); if (n) bits.push(n.textContent); });
    bits.push(el.getAttribute("aria-label") || "", el.getAttribute("placeholder") || "");
    if (!bits.join("").trim()) bits.push(el.name || "", el.id || "");
    return norm(bits.join(" ").replace(/\*/g, " "));
  }

  function controls(selector) {
    return Array.from(document.querySelectorAll(selector)).filter(visible);
  }

  const TEXT_INPUTS = 'input:not([type]), input[type="text"], input[type="search"], input[type="number"], textarea';

  function isEmpty(el) {
    return !String(el.value || "").trim();
  }

  function setValue(el, value) {
    const proto = Object.getPrototypeOf(el);
    const desc = Object.getOwnPropertyDescriptor(proto, "value");
    if (desc && desc.set) desc.set.call(el, value); else el.value = value;
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
  }

  // Typeahead boxes (pick-from-a-list widgets) are not plain text.
  const SEARCH_INPUT = 'input[data-automation-id="searchBox"], input[role="combobox"], input[aria-haspopup="listbox"], input[aria-autocomplete="list"]';
  function isSearchInput(el) { return el.matches && el.matches(SEARCH_INPUT); }

  function fillText(el, value) {
    if (!value || !isEmpty(el) || el.disabled || el.readOnly || isSearchInput(el)) return false;
    setValue(el, value);
    return true;
  }

  // ---------- choosing among options ----------

  function isPlaceholder(t) {
    return /^(select( one)?|please select|choose( one)?|--+.*--+|)$/i.test((t || "").trim());
  }

  // First option whose text matches one of the patterns, in pattern order.
  function pickByPatterns(texts, patterns) {
    for (const p of patterns) {
      const i = texts.findIndex((t) => p.test(t));
      if (i !== -1) return i;
    }
    return -1;
  }

  function fillSelect(sel, patterns) {
    if (sel.disabled) return false;
    const cur = sel.selectedOptions[0]?.text || "";
    if (sel.value && !isPlaceholder(cur)) return false; // already answered
    const texts = Array.from(sel.options).map((o) => norm(o.text));
    const i = pickByPatterns(texts, patterns);
    if (i === -1 || isPlaceholder(sel.options[i].text)) return false;
    sel.value = sel.options[i].value;
    sel.dispatchEvent(new Event("input", { bubbles: true }));
    sel.dispatchEvent(new Event("change", { bubbles: true }));
    return true;
  }

  function precedingHeading(el) {
    const hs = Array.from(document.querySelectorAll('h1, h2, h3, h4, legend, [role="heading"]'))
      .filter((h) => h.compareDocumentPosition(el) & Node.DOCUMENT_POSITION_FOLLOWING);
    return hs.length ? hs[hs.length - 1].textContent : "";
  }

  // "Pick one" questions drawn as a few checkboxes (Yes / No / I do not want
  // to answer) behave like radios, so they are grouped the same way.
  function checkboxClusters() {
    const boxes = controls('input[type="checkbox"]');
    const seen = new Set(), out = [];
    boxes.forEach((cb) => {
      if (seen.has(cb)) return;
      let box = cb.parentElement;
      while (box && box !== document.body && boxes.filter((b) => box.contains(b)).length < 2) box = box.parentElement;
      if (!box || box === document.body) return;
      const inside = boxes.filter((b) => box.contains(b));
      if (inside.length > 6) return;
      const texts = inside.map((b) => norm(labelText(b) || b.value));
      if (!texts.every((t) => /^(yes|no|i (do not|don'?t|am|identify|have|prefer|choose)|decline|prefer|not )/.test(t))) return;
      inside.forEach((b) => seen.add(b));
      out.push({ question: norm(precedingHeading(inside[0]) + " " + box.textContent.slice(0, 500)), radios: inside, texts });
    });
    return out;
  }

  // Radio groups: the question is the fieldset legend or the nearest text
  // above the first radio; the choices are the radios' own labels.
  function radioGroups() {
    const byName = new Map();
    controls('input[type="radio"]').forEach((r) => {
      if (!r.name) return;
      if (!byName.has(r.name)) byName.set(r.name, []);
      byName.get(r.name).push(r);
    });
    const radios = Array.from(byName.values()).map((radios) => {
      const first = radios[0];
      const fs = first.closest("fieldset");
      const legend = fs?.querySelector("legend");
      let q = legend ? legend.textContent : "";
      if (!norm(q)) {
        let node = first.closest("label") || first;
        let hops = 0;
        while (node && hops < 4 && !norm(q)) {
          let prev = node.previousElementSibling;
          while (prev && !norm(prev.textContent)) prev = prev.previousElementSibling;
          if (prev && !prev.querySelector('input[type="radio"]')) q = prev.textContent;
          node = node.parentElement; hops++;
        }
      }
      return { question: norm(q.replace(/\*/g, " ")), radios, texts: radios.map((r) => norm(labelText(r) || r.value)) };
    });
    return radios.concat(checkboxClusters());
  }

  function fillRadio(group, patterns) {
    if (group.radios.some((r) => r.checked)) return false;
    const i = pickByPatterns(group.texts, patterns);
    if (i === -1) return false;
    group.radios[i].click();
    return true;
  }

  // ---------- custom dropdowns (button + pop-up list, typeahead) ----------

  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  let pending = [];

  function customQuestion(el) {
    let t = "";
    if (el.id) {
      const l = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
      if (l) t = l.textContent;
    }
    if (!norm(t)) {
      const by = el.getAttribute("aria-labelledby");
      if (by) by.split(/\s+/).forEach((id) => { const n = document.getElementById(id); if (n) t += " " + n.textContent; });
    }
    if (!norm(t)) t = el.getAttribute("aria-label") || "";
    if (!norm(t)) {
      let node = el, hops = 0;
      while (node && hops < 3 && !norm(t)) {
        let prev = node.previousElementSibling;
        while (prev && !norm(prev.textContent)) prev = prev.previousElementSibling;
        if (prev && !prev.querySelector("input, select, button")) t = prev.textContent;
        node = node.parentElement; hops++;
      }
    }
    return norm(t.replace(/\*/g, " ").replace(/\b(select one|required)\b/gi, " "));
  }

  const DROPDOWN = 'button[aria-haspopup="listbox"], button[role="combobox"], div[role="combobox"][aria-haspopup="listbox"], div[role="combobox"][tabindex]';
  function customDropdowns() { return controls(DROPDOWN).filter((e) => !e.disabled && e.getAttribute("aria-disabled") !== "true"); }
  function searchInputs() { return controls(SEARCH_INPUT).filter((e) => !e.disabled && !e.readOnly); }

  function hasChoice(input) {
    const box = input.closest('[data-automation-id="multiSelectContainer"], [data-automation-id^="formField"]') || input.parentElement;
    return !isEmpty(input) || !!(box && box.querySelector('[data-automation-id="selectedItem"], [data-automation-id="DELETE_charm"]'));
  }

  function queue(kind, el, re, patterns, label, text) {
    if (!pending.some((p) => p.el === el)) pending.push({ kind, el, re, patterns, label, text });
  }

  // One question, answered in whichever form the page uses.
  function answerChoice(questionRe, patterns, groups, label, typed) {
    // Every control that asks this question gets the answer: the same
    // question can appear as a radio group and again as a dropdown.
    let done = false;
    controls("select").forEach((sel) => {
      if (questionRe.test(labelText(sel)) && fillSelect(sel, patterns)) done = true;
    });
    groups.forEach((g) => {
      if (questionRe.test(g.question) && fillRadio(g, patterns)) done = true;
    });
    customDropdowns().forEach((el) => {
      if (questionRe.test(customQuestion(el)) && isPlaceholder(el.textContent)) queue("list", el, questionRe, patterns, label || "answer");
    });
    searchInputs().forEach((el) => {
      if (typed && questionRe.test(customQuestion(el)) && !hasChoice(el)) queue("search", el, questionRe, patterns, label || "answer", typed);
    });
    return done;
  }

  function visibleOptions(el) {
    const id = el.getAttribute("aria-controls") || el.getAttribute("aria-owns");
    const owned = id && document.getElementById(id);
    return Array.from((owned || document).querySelectorAll('[role="option"]')).filter(visible);
  }

  async function waitOptions(el, ms) {
    const end = Date.now() + (ms || 1500);
    while (Date.now() < end) {
      const o = visibleOptions(el);
      if (o.length) return o;
      await sleep(40);
    }
    return [];
  }

  function press(el, key) {
    el.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true }));
    el.dispatchEvent(new KeyboardEvent("keyup", { key, bubbles: true }));
  }

  function clickLikeUser(el) {
    ["pointerdown", "mousedown", "pointerup", "mouseup", "click"].forEach((t) =>
      el.dispatchEvent(new MouseEvent(t, { bubbles: true, cancelable: true, view: window })));
  }

  async function choose(opts, patterns) {
    const i = pickByPatterns(opts.map((o) => norm(o.textContent)), patterns);
    if (i === -1) return false;
    clickLikeUser(opts[i]);
    await sleep(150);
    return true;
  }

  async function pickCustom(btn, patterns) {
    clickLikeUser(btn);
    const opts = await waitOptions(btn);
    const ok = opts.length && (await choose(opts, patterns));
    if (!ok) { press(btn, "Escape"); press(document.body, "Escape"); return false; }
    return !isPlaceholder(btn.textContent);
  }

  async function pickSearch(input, text, patterns) {
    input.focus();
    setValue(input, text);
    press(input, "Enter");
    let opts = await waitOptions(input, 1800);
    if (!opts.length) { press(input, "ArrowDown"); opts = await waitOptions(input, 800); }
    const ok = opts.length && (await choose(opts, patterns));
    if (!ok) { setValue(input, ""); press(input, "Escape"); return false; }
    return true;
  }

  // Runs the choices queued by run(). One at a time: opening a list closes
  // the others, and a pick (a country, say) can redraw later fields.
  RF.finishCustom = async function () {
    const done = [];
    const items = pending; pending = [];
    for (const it of items) {
      let el = it.el;
      if (!document.contains(el)) {
        const again = (it.kind === "list" ? customDropdowns() : searchInputs()).find((e) => it.re.test(customQuestion(e)));
        if (!again) continue;
        el = again;
      }
      let ok = false;
      try { ok = it.kind === "list" ? await pickCustom(el, it.patterns) : await pickSearch(el, it.text, it.patterns); } catch (e) { ok = false; }
      if (ok) done.push(it.label);
      await sleep(200);
    }
    return done;
  };

  // Questions still waiting for the person, so nothing is missed.
  RF.leftForYou = function () {
    const out = [];
    customDropdowns().forEach((el) => { if (isPlaceholder(el.textContent)) out.push(customQuestion(el)); });
    controls("select").forEach((sel) => { if (isPlaceholder(sel.selectedOptions[0]?.text || "")) out.push(labelText(sel)); });
    radioGroups().forEach((g) => { if (g.question && !g.radios.some((r) => r.checked)) out.push(g.question); });
    return Array.from(new Set(out.map((t) => t.trim()).filter((t) => t.length > 3).map((t) => (t.length > 100 ? t.slice(0, 97) + "..." : t)))).slice(0, 8);
  };

  const YES = [/^yes$/, /^yes[,.]? (i am|i do|i can|i will)\b(?!.*\b(but|not|however)\b)/];
  const NO = [/^no$/, /^no[,.]? (i am not|i do not|i don'?t|i will not)\b/];
  const yn = (v) => (v === "yes" ? YES : NO);

  // ---------- standard answers ----------

  const rx = (re, not) => ({ test: (t) => re.test(t) && !(not && not.test(t)) });
  const esc = (x) => String(x).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const Q = {
    over18: /\b(18|eighteen)\s+(years|or older|or over)|at least (18|eighteen)|over (the age of )?(18|eighteen)|legal (working )?age/,
    prevEmp: /(previously|ever|formerly)\s+(been\s+)?(worked|an employee|employed)|worked (for|at|with) (this|our|the) (company|organi[sz]ation)|former employee/,
    relationship: rx(/personal relationship|related to (a |any )?(current )?(employee|team member)|family member.*(employed|works?)/, /government|public official/),
    restrict: /(agreement|obligation).*(restrict|limit)|non.?compete|restrictive covenant|restricts your ability/,
    govOfficial: rx(/government official|public official|politically exposed/, /related to|relative|family/),
    relatedOfficial: /(related to|relative of|family member of).*(government|public) official/,
    referral: /how did you (hear|find|learn)|how .*hear about|referral source|source of (your )?(application|referral)/,
    auth: /(authori[sz]\w*|eligib\w*)\s+(to\s+)?work|legally\s+(able|permitted|entitled)\s+to\s+work|right\s+to\s+work/,
    sponsor: /sponsor/,
    relocate: /relocat/,
    salary: /(salary|compensation|pay)\s+(expectation|requirement|range|desired)|desired\s+(salary|compensation|pay)|(expected|minimum|target|annual)\s+(base\s+)?(salary|compensation|pay)|salary expectations?/,
    notice: /notice\s+period/,
    start: /(earliest|available|when\s+can\s+you).*start|start.*(earliest|availab)/,
    pronouns: /\bpronouns?\b/,
  };

  // Digits only when the box is numeric ("$150,000" would be rejected there).
  function moneyFor(el, text) {
    const t = String(text || "");
    const numeric = el.type === "number" || /numeric|decimal/.test(el.getAttribute("inputmode") || "") || /\bannual\b|numbers only|digits/.test(labelText(el));
    if (numeric && /^\$?\s*[\d,\.]+\s*$/.test(t)) return t.replace(/[$,\s]/g, "").split(".")[0];
    return t;
  }

  function standardAnswers(a, groups, out) {
    const set = (key, label, re) => {
      const v = a[key];
      if (v !== "yes" && v !== "no") return;
      if (answerChoice(re, yn(v), groups, label)) out.push(label);
    };
    set("work_authorized_us", "work authorization", Q.auth);
    set("needs_sponsorship", "visa sponsorship", Q.sponsor);
    set("willing_to_relocate", "willing to relocate", Q.relocate);
    set("over_18", "18 or older", Q.over18);
    set("previously_employed", "worked here before", Q.prevEmp);
    set("has_employee_relationship", "relationship with an employee", Q.relationship);
    set("restrictive_agreement", "work restriction agreement", Q.restrict);
    set("government_official", "government official", Q.govOfficial);
    set("related_to_official", "related to an official", Q.relatedOfficial);
    const text = (key, label, re, money) => {
      if (!a[key]) return;
      for (const el of controls(TEXT_INPUTS)) {
        if (re.test(labelText(el)) && fillText(el, money ? moneyFor(el, a[key]) : a[key])) { out.push(label); return; }
      }
    };
    text("salary_expectation", "salary expectation", Q.salary, true);
    text("notice_period", "notice period", Q.notice);
    text("earliest_start_date", "start date", Q.start);
    if (a.referral_source) {
      const v = norm(a.referral_source);
      text("referral_source", "how you heard about the job", Q.referral);
      if (answerChoice(Q.referral, [new RegExp("^" + esc(v) + "$"), new RegExp("\\b" + esc(v) + "\\b")], groups, "how you heard about the job", a.referral_source)) out.push("how you heard about the job");
    }
  }

  // ---------- optional self-identification ----------

  const DECLINE = /(decline|prefer not|do not wish|don'?t wish|do not want to|don'?t want to|choose not|not to (say|answer|disclose|identify|specify)|rather not)/;
  const EEO_Q = {
    gender: /\bgender\b/,
    race: /\b(race|ethnicity|racial)\b/,
    veteran: /\bveterans?\b/,
    disability: /\bdisabilit/,
    hispanic: /\bhispanic\b|\blatino\b/,
  };
  const EEO_OPTIONS = {
    gender: {
      "Man": [/^(male|man)$/, /^male\b/],
      "Woman": [/^(female|woman)$/, /^female\b/],
      "Non-binary": [/non.?binary/],
    },
    race: {
      "Asian": [/^asian/],
      "Black or African American": [/black|african american/],
      "Hispanic or Latino": [/hispanic|latin/],
      "White": [/^white|caucasian/],
      "Two or more races": [/two or more|multi.?racial/],
      "Native American or Alaska Native": [/american indian|native american|alaska/],
      "Native Hawaiian or Pacific Islander": [/pacific|hawaiian/],
      "Other": [/^other$/],
    },
    veteran: {
      "Yes": [/identify as one or more|^i am (a )?(protected )?veteran|^yes$/],
      "No": [/^(i am )?not a (protected )?veteran|^no$/],
    },
    hispanic: {
      "Yes": [/^yes\b/, /^hispanic or latino$/],
      "No": [/^no\b/, /^not hispanic/],
    },
    disability: {
      "Yes": [/^yes,? i (have|do)|^yes$/],
      "No": [/^no,? i (do not|don'?t|have no)|^no$/],
    },
  };

  function selfIdentification(eeo, groups, out) {
    Object.keys(EEO_Q).forEach((key) => {
      const v = eeo[key];
      if (!v) return; // blank: leave the question to the person
      const patterns = v === "Decline to answer" ? [DECLINE] : (EEO_OPTIONS[key][v] || []);
      if (!patterns.length) return;
      const label = key === "race" ? "race/ethnicity" : key;
      if (answerChoice(EEO_Q[key], patterns, groups, label)) out.push(label);
    });
  }

  // ---------- work history and education ----------

  const WORK_TITLE = /^(job\s*)?title$|^position( title)?$|^role$|(current|most recent|previous).*(title|position)/;
  const WORK_COMPANY = /^(current |most recent |previous )?(company|employer)( name)?$|^organi[sz]ation( name)?$/;
  const SCHOOL = /^(school|university|college|institution)( name)?$|^school or university$/;
  const DEGREE = /^degree( type)?$|^level of education$/;
  const FIELD = /^(field of study|major|discipline|area of study)$/;
  const START = /^(start|from)( date)?(\s*\(.*\))?$|start date/;
  const END = /^(end|to)( date)?(\s*\(.*\))?$|end date/;
  const DESC = /(description|responsibilit|summary|duties|what you did)/;

  function byLabel(re, scope) {
    return Array.from((scope || document).querySelectorAll(TEXT_INPUTS + ", select")).filter((el) => visible(el) && re.test(labelText(el)));
  }

  // The block (one job or one school) a field belongs to: the largest
  // ancestor that holds only that one entry's fields, not another entry's
  // and not the other section's.
  function blockOf(el, ownRe, otherRe) {
    let best = el.parentElement, node = el.parentElement, hops = 0;
    while (node && node !== document.body && hops < 8) {
      const own = byLabel(ownRe, node).length;
      const other = byLabel(otherRe, node).length;
      const n = node.querySelectorAll("input, select, textarea").length;
      if (own > 1 || other > 0 || n > 24) break;
      best = node; node = node.parentElement; hops++;
    }
    return best;
  }

  function monthYear(str) {
    const m = String(str || "").match(/([A-Za-z]{3,9})\.?\s+(\d{4})|(\d{1,2})[\/-](\d{4})|(\d{4})/);
    if (!m) return null;
    const months = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"];
    if (m[1]) { const mi = months.indexOf(m[1].slice(0, 3).toLowerCase()); return { month: mi + 1, year: Number(m[2]) }; }
    if (m[3]) return { month: Number(m[3]), year: Number(m[4]) };
    return { month: 0, year: Number(m[5]) };
  }

  function dateFor(el, str) {
    const d = monthYear(str);
    if (!d) return str || "";
    const hint = norm((el.getAttribute("placeholder") || "") + " " + (el.getAttribute("aria-label") || ""));
    const mm = d.month ? String(d.month).padStart(2, "0") : "";
    if (/mm\s*[\/-]\s*yyyy/.test(hint)) return mm ? `${mm}/${d.year}` : "";
    if (/^yyyy$|\byyyy\b(?!.*mm)/.test(hint)) return String(d.year);
    if (/month/.test(hint) && /year/.test(hint)) return mm ? `${mm}/${d.year}` : String(d.year);
    return str;
  }

  function fillBlock(block, pairs, out, label) {
    let any = false;
    pairs.forEach(([re, value, isDate]) => {
      if (!value) return;
      const el = byLabel(re, block).find((x) => x.tagName !== "SELECT" && isEmpty(x));
      if (el && fillText(el, isDate ? dateFor(el, value) : value)) any = true;
    });
    if (any) out.push(label);
  }

  function history(p, out) {
    // Jobs: the Nth job-title field gets the Nth entry (most recent first).
    // Fields that already have text are skipped, so pressing Autofill again
    // after adding another block fills the new block with the next entry.
    byLabel(WORK_TITLE).filter((x) => x.tagName !== "SELECT").forEach((titleEl, i) => {
      const w = p.work[i];
      if (!w) return;
      const block = blockOf(titleEl, WORK_TITLE, SCHOOL);
      fillBlock(block, [
        [WORK_TITLE, w.title], [WORK_COMPANY, w.company],
        [START, w.start, true], [END, w.current ? "" : w.end, true],
        [DESC, w.summary],
      ], out, `job ${i + 1}`);
    });
    byLabel(SCHOOL).filter((x) => x.tagName !== "SELECT").forEach((schoolEl, i) => {
      const e = p.education[i];
      if (!e) return;
      const block = blockOf(schoolEl, SCHOOL, WORK_TITLE);
      fillBlock(block, [
        [SCHOOL, e.school], [DEGREE, e.degree], [FIELD, e.field],
        [START, e.start, true], [END, e.end, true],
      ], out, `school ${i + 1}`);
    });
  }

  // ---------- saved answers ----------

  const STOP = new Set("a an the to of in on at for and or you your do does did are is be it this that with we our us please tell describe about".split(" "));

  function tokens(s) {
    return new Set(norm(s).replace(/[^a-z0-9 ]/g, " ").split(" ").filter((w) => w.length > 2 && !STOP.has(w)));
  }

  function similar(a, b) {
    const A = tokens(a), B = tokens(b);
    if (A.size < 2 || B.size < 2) return false;
    let hit = 0;
    A.forEach((w) => { if (B.has(w)) hit++; });
    return hit / Math.min(A.size, B.size) >= 0.75 && hit / Math.max(A.size, B.size) >= 0.5;
  }

  function savedAnswers(list, out) {
    if (!list || !list.length) return;
    controls("textarea, " + TEXT_INPUTS).forEach((el) => {
      if (!isEmpty(el) || el.disabled) return;
      const label = labelText(el);
      if (label.length < 8) return;
      const hit = list.find((qa) => similar(label, qa.question));
      if (hit && fillText(el, hit.answer)) out.push("saved answer");
    });
  }

  // A saved answer also answers a question that is a list of choices (a
  // dropdown or radio buttons), but only when it points at exactly one
  // option: the same text, yes or no, or a phrase only one option contains.
  // Anything less clear is left for the person. Never a guess.
  function tidyAnswer(answer) {
    return norm(answer).replace(/[.!\s]+$/, "");
  }

  function choicePatterns(answer) {
    const a = tidyAnswer(answer);
    if (!a || a.length > 80) return [];
    const list = [{ test: (t) => t === a }];
    if (a === "yes" || a === "no") list.push(...yn(a));
    return list;
  }

  function choiceIndex(texts, answer) {
    const a = tidyAnswer(answer);
    if (!a || a.length > 80) return -1;
    const real = (t) => t && !isPlaceholder(t);
    const exact = texts.map((t, i) => (real(t) && t === a ? i : -1)).filter((i) => i !== -1);
    if (exact.length === 1) return exact[0];
    if (exact.length > 1) return -1;
    if (a === "yes" || a === "no") {
      const i = pickByPatterns(texts, yn(a));
      return i !== -1 && real(texts[i]) ? i : -1;
    }
    if (a.length < 3) return -1;
    const re = new RegExp("(^|[^a-z0-9])" + esc(a) + "([^a-z0-9]|$)");
    const part = texts.map((t, i) => (real(t) && re.test(t) ? i : -1)).filter((i) => i !== -1);
    return part.length === 1 ? part[0] : -1;
  }

  function savedChoices(list, groups, out) {
    if (!list || !list.length) return;
    const find = (question) => (question && question.length >= 8 ? list.find((qa) => similar(question, qa.question)) : null);
    controls("select").forEach((sel) => {
      if (sel.disabled) return;
      if (sel.value && !isPlaceholder(sel.selectedOptions[0]?.text || "")) return;
      const hit = find(labelText(sel));
      if (!hit) return;
      const i = choiceIndex(Array.from(sel.options).map((o) => norm(o.text)), hit.answer);
      if (i === -1) return;
      sel.value = sel.options[i].value;
      sel.dispatchEvent(new Event("input", { bubbles: true }));
      sel.dispatchEvent(new Event("change", { bubbles: true }));
      out.push("saved answer");
    });
    groups.forEach((g) => {
      if (g.radios.some((r) => r.checked)) return;
      const hit = find(g.question);
      if (!hit) return;
      const i = choiceIndex(g.texts, hit.answer);
      if (i === -1) return;
      g.radios[i].click();
      out.push("saved answer");
    });
    customDropdowns().forEach((el) => {
      if (!isPlaceholder(el.textContent)) return;
      const q = customQuestion(el);
      const hit = find(q);
      const patterns = hit ? choicePatterns(hit.answer) : [];
      if (patterns.length) queue("list", el, { test: (t) => similar(t, hit.question) }, patterns, "saved answer");
    });
  }

  // ---------- attaching the resume file ----------

  // File inputs are usually hidden behind a styled button, so visibility is
  // not required here. The text around the input says what it is for.
  function fileInputs() {
    return Array.from(document.querySelectorAll('input[type="file"]')).filter((el) => !el.disabled);
  }

  function contextOf(el) {
    const box = el.closest("div, fieldset, section, li, label") || el.parentElement;
    return norm(labelText(el) + " " + (el.name || "") + " " + (el.id || "") + " " + (box ? box.textContent : "").slice(0, 300));
  }

  function acceptsFile(el, file) {
    const accept = norm(el.getAttribute("accept"));
    if (!accept) return true;
    const ext = "." + file.name.split(".").pop().toLowerCase();
    return accept.split(",").map((x) => x.trim()).some((a) => a === ext || a === file.type || (a.endsWith("/*") && file.type.startsWith(a.slice(0, -1))));
  }

  const RESUME_CTX = /\b(resume|r[eé]sum[eé]|cv|curriculum)\b/;
  const OTHER_CTX = /(cover\s*letter|transcript|portfolio|writing sample|photo|picture|certificate|reference|license)/;

  // The input meant for a resume, or null. A single unlabeled upload field is
  // taken to be the resume only when nothing nearby says it is something else.
  function resumeInput(file, replace) {
    // A box that already holds a file is left alone, except one this extension
    // filled itself when the person asks for the tailored resume instead.
    const free = (el) => !(el.files && el.files.length) || (replace && el.dataset.riseplyAttached === "1");
    const inputs = fileInputs().filter((el) => free(el) && acceptsFile(el, file));
    const labeled = inputs.find((el) => { const c = contextOf(el); return RESUME_CTX.test(c) && !/cover\s*letter/.test(labelText(el)); });
    if (labeled) return labeled;
    const all = fileInputs();
    if (all.length === 1 && inputs.length === 1 && !OTHER_CTX.test(contextOf(inputs[0]))) return inputs[0];
    return null;
  }

  RF.hasResumeInput = function () { return fileInputs().length > 0; };

  // `data` is base64 from the Riseply server. Chrome lets a page script give a
  // file input a file built in memory (the same thing a drag-and-drop does).
  RF.attachResume = function (payload, opts) {
    try {
      const bin = atob(payload.data);
      const bytes = new Uint8Array(bin.length);
      for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
      const file = new File([bytes], payload.filename, { type: payload.content_type });
      const input = resumeInput(file, !!(opts && opts.replace));
      if (!input) return false;
      const dt = new DataTransfer();
      dt.items.add(file);
      input.files = dt.files;
      input.dataset.riseplyAttached = "1";
      input.dispatchEvent(new Event("input", { bubbles: true }));
      input.dispatchEvent(new Event("change", { bubbles: true }));
      return true;
    } catch (e) {
      return false;
    }
  };


  // ---------- site login and moving on ----------

  function loginFields() {
    const pws = controls('input[type="password"]').filter((e) => !e.disabled);
    // Two password boxes means "create an account", which is never filled.
    if (pws.length !== 1) return null;
    const pw = pws[0];
    let scope = pw.form || pw.parentElement;
    for (let i = 0; i < 4 && scope && scope !== document.body; i++) {
      if (scope.querySelectorAll("input").length > 1) break;
      scope = scope.parentElement;
    }
    scope = scope || document;
    const before = Array.from(scope.querySelectorAll('input:not([type]), input[type="text"], input[type="email"]'))
      .filter((e) => visible(e) && !e.disabled && !e.readOnly)
      .filter((e) => e.compareDocumentPosition(pw) & Node.DOCUMENT_POSITION_FOLLOWING);
    return { pw, user: before.length ? before[before.length - 1] : null, scope };
  }

  RF.hasLogin = function () {
    return !!loginFields();
  };

  RF.fillLogin = function (cred) {
    const f = loginFields();
    const out = [];
    if (!f || !cred) return out;
    if (f.user && cred.username && fillText(f.user, cred.username)) out.push("username");
    if (cred.password && fillText(f.pw, cred.password)) out.push("password");
    return out;
  };

  const SUBMIT_BTN = /^(submit|submit application|submit your application|send application)$/;
  const LOGIN_BTN = /^(log ?in|sign ?in)$/;
  const NEXT_BTN = /^(next|next step|next page|continue|continue application|save (and|&) continue|proceed)$/;

  function buttonText(el) {
    return norm(el.value || el.getAttribute("aria-label") || el.textContent).replace(/[→›»>]+$/, "").trim();
  }

  function clickables() {
    return Array.from(document.querySelectorAll('button, a, [role="button"], input[type="submit"], input[type="button"]'))
      .filter((e) => visible(e) && !e.disabled && e.getAttribute("aria-disabled") !== "true");
  }

  // The control that moves a form on a step: "Log in" on a sign-in page,
  // otherwise "Next" or "Continue". Never a final Submit.
  RF.findAdvance = function () {
    const f = loginFields();
    const all = clickables();
    if (f) {
      const l = all.find((e) => LOGIN_BTN.test(buttonText(e)));
      if (l) return { el: l, label: buttonText(l), kind: "login" };
    }
    const n = all.find((e) => NEXT_BTN.test(buttonText(e)));
    if (n) return { el: n, label: buttonText(n), kind: "next" };
    const sub = all.find((e) => SUBMIT_BTN.test(buttonText(e)));
    return sub ? { el: sub, label: buttonText(sub), kind: "submit" } : null;
  };

  // ---------- address, phone, signature date ----------

  const STATES = "AL Alabama,AK Alaska,AZ Arizona,AR Arkansas,CA California,CO Colorado,CT Connecticut,DE Delaware,DC District of Columbia,FL Florida,GA Georgia,HI Hawaii,ID Idaho,IL Illinois,IN Indiana,IA Iowa,KS Kansas,KY Kentucky,LA Louisiana,ME Maine,MD Maryland,MA Massachusetts,MI Michigan,MN Minnesota,MS Mississippi,MO Missouri,MT Montana,NE Nebraska,NV Nevada,NH New Hampshire,NJ New Jersey,NM New Mexico,NY New York,NC North Carolina,ND North Dakota,OH Ohio,OK Oklahoma,OR Oregon,PA Pennsylvania,RI Rhode Island,SC South Carolina,SD South Dakota,TN Tennessee,TX Texas,UT Utah,VT Vermont,VA Virginia,WA Washington,WV West Virginia,WI Wisconsin,WY Wyoming".split(",").map((x) => [x.slice(0, 2), x.slice(3)]);

  function statePatterns(v) {
    const t = norm(v);
    const hit = STATES.find(([ab, name]) => ab.toLowerCase() === t || name.toLowerCase() === t);
    const names = hit ? [hit[0].toLowerCase(), hit[1].toLowerCase()] : [t];
    return names.map((n) => new RegExp("^" + esc(n) + "$")).concat(names.map((n) => new RegExp("^" + esc(n) + "\\b")));
  }

  function countryPatterns(v) {
    const t = norm(v);
    const us = /^(us|usa|u\.s\.a?\.?|united states( of america)?)$/.test(t);
    const base = us ? ["united states of america", "united states", "usa"] : [t];
    return base.map((n) => new RegExp("^" + esc(n) + "$")).concat(base.map((n) => new RegExp("^" + esc(n) + "\\b")), us ? [/\(\+1\)/] : []);
  }

  function textByLabel(re, value) {
    if (!value) return false;
    for (const el of controls(TEXT_INPUTS)) {
      if (re.test(labelText(el)) && fillText(el, value)) return true;
    }
    return false;
  }

  function contactAnswers(c, groups, out) {
    // Country first: a country can change which other fields the page shows.
    if (c.country && answerChoice(/^country( ?\/ ?region)?$/, countryPatterns(c.country), groups, "country")) out.push("country");
    else if (c.country && textByLabel(/^country( ?\/ ?region)?$/, c.country)) out.push("country");
    if (textByLabel(/^(street )?address( line)?( 1| one)?$|^street( address)?$|^address 1$/, c.address_line1)) out.push("address");
    if (textByLabel(/^(address line 2|apartment|apt|suite|unit)\b|address( line)? (2|two)$/, c.address_line2)) out.push("address line 2");
    if (textByLabel(/^(city|town)( ?\/ ?(city|town))?$/, c.city)) out.push("city");
    if (c.state) {
      const re = /^(state|province)( ?\/ ?(state|province|territory|region))*$/;
      if (answerChoice(re, statePatterns(c.state), groups, "state")) out.push("state");
      else if (textByLabel(re, c.state)) out.push("state");
    }
    if (textByLabel(/\b(zip|postal)\b( code)?/, c.postal_code)) out.push("postal code");
    const type = c.phone_type || "Mobile";
    const typePats = [new RegExp("^" + esc(norm(type)) + "\\b")].concat(type === "Mobile" ? [/cell/] : []);
    const typeLabel = c.phone_type ? "phone type" : "phone type (Mobile by default)";
    if (answerChoice(/phone (device )?type|device type/, typePats, groups, typeLabel)) out.push(typeLabel);
    if (c.country && answerChoice(/(country|phone|dial\w*)\s*(phone )?code|^country phone/, countryPatterns(c.country), groups, "phone country code", c.country)) out.push("phone country code");
  }

  // The "Date" next to a name on self-identification forms: today.
  function signatureDate(out) {
    const d = new Date();
    const mm = String(d.getMonth() + 1).padStart(2, "0"), dd = String(d.getDate()).padStart(2, "0"), yyyy = String(d.getFullYear());
    const plain = (e) => norm(labelText(e)).replace(/\brequired\b/g, "").trim();
    for (const el of controls("input")) {
      if (el.disabled || el.readOnly || !isEmpty(el) || plain(el) !== "date") continue;
      if (el.type === "date") { setValue(el, `${yyyy}-${mm}-${dd}`); out.push("date"); return; }
      const wrap = el.closest('[data-automation-id="dateInputWrapper"], [data-automation-id^="formField"]') || el.parentElement;
      const seg = wrap ? Array.from(wrap.querySelectorAll('input[data-automation-id*="dateSection"]')) : [];
      if (seg.length >= 3) {
        const by = (w) => seg.find((x) => (x.getAttribute("data-automation-id") || "").toLowerCase().includes(w));
        const [m, da, y] = [by("month"), by("day"), by("year")];
        if (m && da && y) { setValue(m, mm); setValue(da, dd); setValue(y, yyyy); out.push("date"); return; }
      }
      const hint = norm(el.getAttribute("placeholder") || "");
      const val = /dd\s*[\/-]\s*mm/.test(hint) ? `${dd}/${mm}/${yyyy}` : /yyyy\s*[-\/]\s*mm/.test(hint) ? `${yyyy}-${mm}-${dd}` : `${mm}/${dd}/${yyyy}`;
      setValue(el, val); out.push("date"); return;
    }
  }

  // ---------- entry point ----------

  RF.run = function (profile) {
    const p = profile || {};
    const out = [];
    pending = [];
    const groups = radioGroups();
    contactAnswers(p.contact || {}, groups, out);
    standardAnswers(p.answers || {}, groups, out);
    selfIdentification(p.eeo || {}, groups, out);
    signatureDate(out);
    history({ work: p.work || [], education: p.education || [] }, out);
    savedAnswers(p.saved_answers || [], out);
    savedChoices(p.saved_answers || [], groups, out);
    return { filled: out };
  };

  RF.isEmptyProfile = function (p) {
    if (!p) return true;
    const a = Object.values(p.answers || {}).some(Boolean);
    const e = Object.values(p.eeo || {}).some(Boolean);
    const c = Object.values(p.contact || {}).some(Boolean);
    return !(a || e || c || (p.work || []).length || (p.education || []).length || (p.saved_answers || []).length);
  };

  window.RisePlyFill = RF;
})();
