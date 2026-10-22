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
    return norm(bits.join(" "));
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

  function fillText(el, value) {
    if (!value || !isEmpty(el) || el.disabled || el.readOnly) return false;
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

  // Radio groups: the question is the fieldset legend or the nearest text
  // above the first radio; the choices are the radios' own labels.
  function radioGroups() {
    const byName = new Map();
    controls('input[type="radio"]').forEach((r) => {
      if (!r.name) return;
      if (!byName.has(r.name)) byName.set(r.name, []);
      byName.get(r.name).push(r);
    });
    return Array.from(byName.values()).map((radios) => {
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
      return { question: norm(q), radios, texts: radios.map((r) => norm(labelText(r) || r.value)) };
    });
  }

  function fillRadio(group, patterns) {
    if (group.radios.some((r) => r.checked)) return false;
    const i = pickByPatterns(group.texts, patterns);
    if (i === -1) return false;
    group.radios[i].click();
    return true;
  }

  // One question, answered in whichever form the page uses.
  function answerChoice(questionRe, patterns, groups) {
    let done = false;
    controls("select").forEach((sel) => {
      if (done || !questionRe.test(labelText(sel))) return;
      done = fillSelect(sel, patterns);
    });
    groups.forEach((g) => {
      if (done || !questionRe.test(g.question)) return;
      done = fillRadio(g, patterns);
    });
    return done;
  }

  const YES = [/^yes$/, /^yes[,.]? (i am|i do|i can|i will)\b(?!.*\b(but|not|however)\b)/];
  const NO = [/^no$/, /^no[,.]? (i am not|i do not|i don'?t|i will not)\b/];
  const yn = (v) => (v === "yes" ? YES : NO);

  // ---------- standard answers ----------

  const Q = {
    auth: /(authori[sz]\w*|eligib\w*)\s+(to\s+)?work|legally\s+(able|permitted|entitled)\s+to\s+work|right\s+to\s+work/,
    sponsor: /sponsor/,
    relocate: /relocat/,
    salary: /(salary|compensation|pay)\s+(expectation|requirement|range|desired)|desired\s+(salary|compensation|pay)|expected\s+(salary|compensation|pay)/,
    notice: /notice\s+period/,
    start: /(earliest|available|when\s+can\s+you).*start|start.*(earliest|availab)/,
    pronouns: /\bpronouns?\b/,
  };

  function standardAnswers(a, groups, out) {
    const set = (key, label, re) => {
      const v = a[key];
      if (v !== "yes" && v !== "no") return;
      if (answerChoice(re, yn(v), groups)) out.push(label);
    };
    set("work_authorized_us", "work authorization", Q.auth);
    set("needs_sponsorship", "visa sponsorship", Q.sponsor);
    set("willing_to_relocate", "willing to relocate", Q.relocate);
    const text = (key, label, re) => {
      if (!a[key]) return;
      for (const el of controls(TEXT_INPUTS)) {
        if (re.test(labelText(el)) && fillText(el, a[key])) { out.push(label); return; }
      }
    };
    text("salary_expectation", "salary expectation", Q.salary);
    text("notice_period", "notice period", Q.notice);
    text("earliest_start_date", "start date", Q.start);
  }

  // ---------- optional self-identification ----------

  const DECLINE = /(decline|prefer not|do not wish|don'?t wish|choose not|not to (say|answer|disclose|identify|specify)|rather not)/;
  const EEO_Q = {
    gender: /\bgender\b/,
    race: /\b(race|ethnicity|racial)\b/,
    veteran: /\bveteran\b/,
    disability: /\bdisabilit/,
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
      "No": [/not a (protected )?veteran|^no$/],
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
      if (answerChoice(EEO_Q[key], patterns, groups)) out.push(key === "race" ? "race/ethnicity" : key);
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
  function resumeInput(file) {
    const inputs = fileInputs().filter((el) => !(el.files && el.files.length) && acceptsFile(el, file));
    const labeled = inputs.find((el) => { const c = contextOf(el); return RESUME_CTX.test(c) && !/cover\s*letter/.test(labelText(el)); });
    if (labeled) return labeled;
    const all = fileInputs();
    if (all.length === 1 && inputs.length === 1 && !OTHER_CTX.test(contextOf(inputs[0]))) return inputs[0];
    return null;
  }

  RF.hasResumeInput = function () { return fileInputs().length > 0; };

  // `data` is base64 from the Riseply server. Chrome lets a page script give a
  // file input a file built in memory (the same thing a drag-and-drop does).
  RF.attachResume = function (payload) {
    try {
      const bin = atob(payload.data);
      const bytes = new Uint8Array(bin.length);
      for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
      const file = new File([bytes], payload.filename, { type: payload.content_type });
      const input = resumeInput(file);
      if (!input) return false;
      const dt = new DataTransfer();
      dt.items.add(file);
      input.files = dt.files;
      input.dispatchEvent(new Event("input", { bubbles: true }));
      input.dispatchEvent(new Event("change", { bubbles: true }));
      return true;
    } catch (e) {
      return false;
    }
  };

  // ---------- entry point ----------

  RF.run = function (profile) {
    const p = profile || {};
    const out = [];
    const groups = radioGroups();
    standardAnswers(p.answers || {}, groups, out);
    selfIdentification(p.eeo || {}, groups, out);
    history({ work: p.work || [], education: p.education || [] }, out);
    savedAnswers(p.saved_answers || [], out);
    return { filled: out };
  };

  RF.isEmptyProfile = function (p) {
    if (!p) return true;
    const a = Object.values(p.answers || {}).some(Boolean);
    const e = Object.values(p.eeo || {}).some(Boolean);
    return !(a || e || (p.work || []).length || (p.education || []).length || (p.saved_answers || []).length);
  };

  window.RisePlyFill = RF;
})();
