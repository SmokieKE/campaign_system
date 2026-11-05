import sys
print('Updating wards to Luckysummer...', file=sys.stderr)
from app import app, db, Contact

with app.app_context():
    # Get all contacts
    contacts = Contact.query.all()
    print(f'Total contacts: {len(contacts)}')
    
    # Update all wards to Luckysummer
    for c in contacts:
        old_ward = c.ward
        c.ward = 'Luckysummer'
        print(f'  {c.name}: {old_ward} -> Luckysummer')
    
    db.session.commit()
    print('\nContacts updated successfully!')
    
    # Verify
    wards = [r[0] for r in db.session.query(Contact.ward).distinct() if r[0]]
    print(f'\nNew wards in DB: {wards}')