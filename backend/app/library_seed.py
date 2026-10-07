"""Starter Library content, seeded once on first startup (idempotent: only
when the table is empty), same approach as kb_seed.py. These are
well-known, long-lived free resources pointed at their stable top-level
pages. An admin should skim them and edit or add to the list from the
Library page -- sites do reorganize over time."""
from sqlalchemy.orm import Session
from app import models

SEED_ITEMS = [
    ("freeCodeCamp", "https://www.freecodecamp.org/", "Free, project-based courses and certifications in web development, data analysis, Python, and more.", "course", "programming,web development,javascript,python,data analysis", "beginner", "free"),
    ("The Odin Project", "https://www.theodinproject.com/", "Free full-stack web development curriculum built around building real projects.", "course", "web development,programming,javascript,full stack", "beginner", "free"),
    ("Harvard CS50", "https://cs50.harvard.edu/x/", "Harvard's free introduction to computer science and programming.", "course", "programming,computer science,software engineering", "beginner", "free"),
    ("MDN Web Docs", "https://developer.mozilla.org/", "The standard reference for HTML, CSS, and JavaScript.", "reference", "web development,javascript,html,css,frontend", "all", "free"),
    ("roadmap.sh", "https://roadmap.sh/", "Step-by-step learning roadmaps for developer roles such as frontend, backend, DevOps, and data.", "reference", "software engineering,devops,backend,frontend,career", "all", "free"),
    ("SQLBolt", "https://sqlbolt.com/", "Short interactive lessons that teach SQL by doing.", "practice", "sql,data analysis,databases", "beginner", "free"),
    ("Kaggle Learn", "https://www.kaggle.com/learn", "Short free courses on Python, pandas, SQL, data visualization, and machine learning.", "course", "data analysis,python,sql,machine learning,data science", "beginner", "free"),
    ("Khan Academy", "https://www.khanacademy.org/", "Free lessons in math, statistics, economics, finance, and more, with practice exercises.", "course", "statistics,math,economics,finance,accounting", "beginner", "free"),
    ("MIT OpenCourseWare", "https://ocw.mit.edu/", "Free materials from real MIT courses across engineering, science, business, and more.", "course", "engineering,computer science,business,math,science", "intermediate", "free"),
    ("Grow with Google Career Certificates", "https://grow.google/certificates/", "Job-focused certificate programs in data analytics, UX design, project management, and IT support.", "course", "data analytics,ux design,project management,it support", "beginner", "paid"),
    ("Nielsen Norman Group articles", "https://www.nngroup.com/articles/", "Research-based articles on usability and UX design.", "article", "ux design,usability,user research,product design", "all", "free"),
    ("The Scrum Guide", "https://scrumguides.org/", "The official, short definition of Scrum.", "reference", "project management,agile,scrum,product management", "all", "free"),
    ("OWASP Top Ten", "https://owasp.org/www-project-top-ten/", "The standard awareness document for the most critical web application security risks.", "reference", "cybersecurity,application security,security engineering", "intermediate", "free"),
    ("NIST Cybersecurity Framework", "https://www.nist.gov/cyberframework", "The widely used framework for organizing and improving cybersecurity programs.", "reference", "cybersecurity,risk management,compliance,governance", "intermediate", "free"),
]


def seed_library_if_empty(db: Session):
    if db.query(models.LibraryItem).first():
        return
    for title, url, desc, rtype, fields, level, cost in SEED_ITEMS:
        db.add(models.LibraryItem(
            title=title, url=url, description=desc, resource_type=rtype,
            fields=fields, level=level, cost=cost, active=True,
        ))
    db.commit()
