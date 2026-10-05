"""Global reference options supplied for Zimbabwe curriculum setup.

This is a selection library, not a mandate: activation creates/reuses the school's
existing Subject records. Activities never become academic Subject records.
"""

from hashlib import sha256


GROUPS = {
    "ECD / Infant / Primary": ["Indigenous Language", "English Language", "Mathematics", "Science and Technology", "Social Science", "Physical Education and Arts"],
    "Secondary / Core": ["Mathematics", "Functional Mathematics", "Combined Science", "Heritage Studies", "English Language", "Indigenous Language"],
    "Secondary / Languages and Literature": ["Literature in English", "Literature in Indigenous Languages", "Foreign Languages", "English for Communication", "Communication Skills"],
    "Secondary / Sciences": ["Computer Science", "Geography", "Physics", "Chemistry", "Biology", "Additional Mathematics", "Pure Mathematics", "Statistics", "Agriculture", "Agriculture Engineering", "Crop Science", "Animal Science", "Horticulture", "Sports Science"],
    "Secondary / Humanities": ["History", "Sociology", "Economic History", "Family and Religious Studies", "Guidance and Counselling and Life Skills Education"],
    "Secondary / Commercials": ["Business and Enterprise Skills", "Commerce", "Commercial Studies", "Economics", "Principles of Accounts", "Accounting", "Business Studies"],
    "Secondary / Technical and Vocational": ["Wood Technology and Design", "Metal Technology and Design", "Technical Graphics and Design", "Building Technology and Design", "Textiles Technology and Design", "Textile Technology and Design", "Food Technology and Design", "Home Management and Design", "Design and Technology"],
    "Secondary / Arts and PE": ["Art", "Dance", "Musical Arts", "Theatre Arts", "Physical Education, Sport and Mass Displays", "Film", "Sport Management"],
}
ACTIVITIES = ["Assembly", "Break", "Lunch", "Sports", "Reading", "Clubs", "Study", "Other"]
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def subject_key(name):
    return "ZW-" + sha256(name.encode()).hexdigest()[:16]


SUBJECTS = {subject_key(name): name for names in GROUPS.values() for name in names}


def library():
    return {"groups": [{"name": group, "subjects": [{"key": subject_key(name), "name": name} for name in names]} for group, names in GROUPS.items()], "activities": ACTIVITIES}
