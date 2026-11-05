import sys
print('Starting script...', file=sys.stderr)
from app import app, db, Contact

print('Script running...', file=sys.stderr)
with app.app_context():
    # Get all distinct wards
    wards = [r[0] for r in db.session.query(Contact.ward).distinct() if r[0]]
    print('Current wards in DB:', wards)
    
    # List all contacts
    contacts = Contact.query.all()
    print(f'\nTotal contacts: {len(contacts)}')
    for c in contacts:
        print(f'  {c.name}: {c.ward}')