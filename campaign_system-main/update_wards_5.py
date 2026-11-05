import sys
from app import app, db, Contact

print('Updating wards to Cherangany Constituency...', file=sys.stderr)

# The 7 official wards of Cherangany Constituency
wards = [
    'Sinyerere', 
    'Makutano', 
    'Kaplamai', 
    'Motosiet', 
    'Cherangany/Suwerwa', 
    'Chepsiro/Kiptoror', 
    'Sitatunga'
]

with app.app_context():
    contacts = Contact.query.all()
    print(f'Total contacts found: {len(contacts)}')
    
    # Evenly distribute existing contacts across the Cherangany wards
    for i, c in enumerate(contacts):
        old_ward = getattr(c, 'ward', 'None')
        new_ward = wards[i % len(wards)]
        c.ward = new_ward
        print(f'  {c.name}: {old_ward} -> {new_ward}')
    
    db.session.commit()
    print('\nContacts successfully reassigned to Cherangany wards!')
    
    # Verify the distinct changes directly against MariaDB
    distinct_wards = [r[0] for r in db.session.query(Contact.ward).distinct() if r[0]]
    print(f'\nVerified wards now in DB: {distinct_wards}')
