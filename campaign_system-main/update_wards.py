import sys
print('Starting update script...', file=sys.stderr)
from app import app, db, Contact

# Cherangany Constituency wards
cherangany_wards = [
    'Sinyerere', 
    'Makutano', 
    'Kaplamai', 
    'Motosiet', 
    'Cherangany/Suwerwa', 
    'Chepsiro/Kiptoror', 
    'Sitatunga'
]

with app.app_context():
    # Get all contacts
    contacts = Contact.query.all()
    print(f'Total contacts: {len(contacts)}')
    
    # Update each contact with a Cherangany ward
    for i, c in enumerate(contacts):
        old_ward = getattr(c, 'ward', 'None')
        new_ward = cherangany_wards[i % len(cherangany_wards)]
        c.ward = new_ward
        print(f'  {c.name}: {old_ward} -> {new_ward}')
    
    db.session.commit()
    print('\nContacts updated successfully!')
    
    # Verify
    wards = [r[0] for r in db.session.query(Contact.ward).distinct() if r[0]]
    print(f'\nNew wards in DB: {wards}')