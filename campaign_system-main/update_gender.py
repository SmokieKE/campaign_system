import sys
from app import app, db, Contact

print('Validating and standardizing contact database attributes...', file=sys.stderr)

with app.app_context():
    contacts = Contact.query.all()
    print(f'Total contacts found in DB: {len(contacts)}')
    
    # Safely scan and enforce data integrity across existing profile structural values
    for c in contacts:
        # Normalize gender formatting to standard Title Case if already present, or assign defaults safely
        if hasattr(c, 'gender') and c.gender:
            if c.gender.strip().lower() in ['male', 'm']:
                c.gender = 'Male'
            elif c.gender.strip().lower() in ['female', 'f']:
                c.gender = 'Female'
            else:
                c.gender = 'Male'  # Fallback default configuration safely
        else:
            c.gender = 'Male'  # Fallback design assignment if missing entirely
            
    db.session.commit()
    print('Contacts updated successfully!')
    
    # Verification query directly against the MariaDB active schema engine layout
    genders = [r[0] for r in db.session.query(Contact.gender).distinct() if r[0]]
    print(f'Active verified Genders in DB: {genders}')