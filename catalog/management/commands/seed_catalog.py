from decimal import Decimal
from django.core.management.base import BaseCommand
from django.utils.text import slugify

from core.models import Tenant
from catalog.models import Category, Product, ProductAttribute


class Command(BaseCommand):
    help = 'Seed catalog data (categories, products, attributes) for all tenants'

    def add_arguments(self, parser):
        parser.add_argument(
            '--flush',
            action='store_true',
            help='Delete existing catalog data before seeding',
        )

    def handle(self, *args, **options):
        tenants = Tenant.objects.filter(is_active=True)

        if not tenants.exists():
            self.stdout.write(self.style.WARNING(
                'No active tenants found. Run "python manage.py seed" first.'
            ))
            return

        if options['flush']:
            self.stdout.write('Flushing existing catalog data...')
            ProductAttribute.objects.all().delete()
            Product.objects.all().delete()
            Category.objects.all().delete()
            self.stdout.write(self.style.SUCCESS('Catalog data flushed.'))

        for tenant in tenants:
            self._seed_tenant(tenant)

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('=' * 60))
        self.stdout.write(self.style.SUCCESS('Catalog seeding complete!'))
        self.stdout.write(self.style.SUCCESS('=' * 60))
        self.stdout.write('')
        self.stdout.write('Login as a tenant admin to see catalog data:')
        self.stdout.write('  admin_acme     / demo123  (Acme Industries)')
        self.stdout.write('  admin_global   / demo123  (Global Supplies Co)')
        self.stdout.write('  admin_techware / demo123  (TechWare Solutions)')
        self.stdout.write('')
        self.stdout.write(self.style.WARNING(
            'Note: Superuser "admin" has no tenant — catalog data '
            'will not appear when logged in as admin.'
        ))

    def _seed_tenant(self, tenant):
        # Check if data already exists
        if Product.objects.filter(tenant=tenant).exists():
            self.stdout.write(self.style.WARNING(
                f'  [{tenant.name}] Catalog data already exists. '
                f'Use --flush to re-seed.'
            ))
            return

        self.stdout.write(f'\n  Seeding catalog for: {tenant.name}')

        # ── Departments ──
        departments_data = [
            ('Electronics', 'Electronic devices and accessories'),
            ('Office Supplies', 'Office and stationery products'),
            ('Safety Equipment', 'Safety and protective gear'),
        ]

        departments = {}
        for name, desc in departments_data:
            dept, _ = Category.objects.get_or_create(
                tenant=tenant,
                slug=slugify(name),
                defaults={
                    'name': name,
                    'description': desc,
                    'is_active': True,
                },
            )
            departments[name] = dept
        self.stdout.write(f'    Created {len(departments)} departments')

        # ── Categories ──
        categories_data = [
            ('Laptops', 'Electronics', 'Laptop computers and notebooks'),
            ('Accessories', 'Electronics', 'Electronic accessories and peripherals'),
            ('Paper Products', 'Office Supplies', 'Paper and printing supplies'),
            ('Writing Instruments', 'Office Supplies', 'Pens, pencils, and markers'),
            ('PPE', 'Safety Equipment', 'Personal Protective Equipment'),
            ('First Aid', 'Safety Equipment', 'First aid and medical supplies'),
        ]

        categories = {}
        for name, parent_name, desc in categories_data:
            cat, _ = Category.objects.get_or_create(
                tenant=tenant,
                slug=slugify(name),
                defaults={
                    'name': name,
                    'parent': departments[parent_name],
                    'description': desc,
                    'is_active': True,
                },
            )
            categories[name] = cat
        self.stdout.write(f'    Created {len(categories)} categories')

        # ── Sub-categories ──
        subcategories_data = [
            ('Business Laptops', 'Laptops', 'Enterprise-grade laptops'),
            ('Gaming Laptops', 'Laptops', 'High-performance gaming laptops'),
            ('Cables', 'Accessories', 'Cables and connectors'),
            ('Adapters', 'Accessories', 'Adapters and converters'),
            ('Copy Paper', 'Paper Products', 'Standard copy and printer paper'),
            ('Notebooks', 'Paper Products', 'Notebooks and notepads'),
            ('Pens', 'Writing Instruments', 'Ballpoint and gel pens'),
            ('Markers', 'Writing Instruments', 'Markers and highlighters'),
            ('Gloves', 'PPE', 'Protective gloves'),
            ('Safety Glasses', 'PPE', 'Protective eyewear'),
            ('First Aid Kits', 'First Aid', 'Complete first aid kits'),
            ('Bandages', 'First Aid', 'Bandages and wound care'),
        ]

        subcategories = {}
        for name, parent_name, desc in subcategories_data:
            subcat, _ = Category.objects.get_or_create(
                tenant=tenant,
                slug=slugify(name),
                defaults={
                    'name': name,
                    'parent': categories[parent_name],
                    'description': desc,
                    'is_active': True,
                },
            )
            subcategories[name] = subcat
        self.stdout.write(f'    Created {len(subcategories)} sub-categories')

        # ── Products ──
        products_data = [
            {
                'sku': 'ELEC-LAP-001',
                'name': 'Dell Latitude 5540',
                'description': '15.6" business laptop with Intel Core i7, 16GB RAM, 512GB SSD',
                'category': subcategories['Business Laptops'],
                'status': 'active',
                'purchase_cost': Decimal('720.00'),
                'wholesale_price': Decimal('799.00'),
                'retail_price': Decimal('899.00'),
                'markup_percentage': Decimal('24.86'),
                'weight': Decimal('1.800'),
                'length': Decimal('35.80'),
                'width': Decimal('23.50'),
                'height': Decimal('1.90'),
                'barcode': '5901234123457',
                'brand': 'Dell',
                'manufacturer': 'Dell Technologies',
                'attributes': [
                    ('Color', 'Silver', 'text'),
                    ('RAM', '16GB', 'text'),
                    ('Storage', '512GB SSD', 'text'),
                ],
            },
            {
                'sku': 'ELEC-LAP-002',
                'name': 'ASUS ROG Strix G16',
                'description': '16" gaming laptop with RTX 4060, 32GB RAM, 1TB SSD',
                'category': subcategories['Gaming Laptops'],
                'status': 'active',
                'purchase_cost': Decimal('1150.00'),
                'wholesale_price': Decimal('1299.00'),
                'retail_price': Decimal('1499.00'),
                'markup_percentage': Decimal('30.35'),
                'weight': Decimal('2.500'),
                'length': Decimal('35.40'),
                'width': Decimal('25.20'),
                'height': Decimal('2.26'),
                'barcode': '5901234123464',
                'brand': 'ASUS',
                'manufacturer': 'ASUSTeK Computer Inc.',
                'attributes': [
                    ('Color', 'Eclipse Gray', 'text'),
                    ('GPU', 'RTX 4060', 'text'),
                    ('Display', '165Hz IPS', 'text'),
                ],
            },
            {
                'sku': 'ELEC-ACC-001',
                'name': 'USB-C Hub 7-in-1',
                'description': 'Multi-port USB-C hub with HDMI, USB-A, SD card reader',
                'category': subcategories['Adapters'],
                'status': 'active',
                'purchase_cost': Decimal('22.00'),
                'wholesale_price': Decimal('35.00'),
                'retail_price': Decimal('45.00'),
                'markup_percentage': Decimal('104.55'),
                'weight': Decimal('0.085'),
                'barcode': '5901234123471',
                'brand': 'Anker',
                'manufacturer': 'Anker Innovations',
                'attributes': [
                    ('Ports', '7', 'number'),
                    ('Color', 'Space Gray', 'text'),
                ],
            },
            {
                'sku': 'ELEC-ACC-002',
                'name': 'USB-C to HDMI Cable 2m',
                'description': '4K@60Hz USB-C to HDMI cable, 2 meter length',
                'category': subcategories['Cables'],
                'status': 'active',
                'purchase_cost': Decimal('8.50'),
                'wholesale_price': Decimal('14.00'),
                'retail_price': Decimal('19.99'),
                'markup_percentage': Decimal('135.18'),
                'weight': Decimal('0.120'),
                'length': Decimal('200.00'),
                'barcode': '5901234123488',
                'brand': 'Belkin',
                'manufacturer': 'Belkin International',
                'attributes': [
                    ('Length', '2m', 'text'),
                    ('Resolution', '4K@60Hz', 'text'),
                ],
            },
            {
                'sku': 'OFFC-PAP-001',
                'name': 'A4 Copy Paper 500-sheet',
                'description': 'Premium white A4 copy paper, 80gsm, 500 sheets per ream',
                'category': subcategories['Copy Paper'],
                'status': 'active',
                'purchase_cost': Decimal('4.50'),
                'wholesale_price': Decimal('6.99'),
                'retail_price': Decimal('8.99'),
                'markup_percentage': Decimal('99.78'),
                'weight': Decimal('2.500'),
                'barcode': '5901234123495',
                'brand': 'Double A',
                'manufacturer': 'Double A Public Company',
                'attributes': [
                    ('GSM', '80', 'number'),
                    ('Sheets', '500', 'number'),
                    ('Size', 'A4', 'text'),
                ],
            },
            {
                'sku': 'OFFC-PAP-002',
                'name': 'Spiral Notebook A5 200-page',
                'description': 'Wire-bound A5 notebook with ruled pages, 200 pages',
                'category': subcategories['Notebooks'],
                'status': 'active',
                'purchase_cost': Decimal('2.20'),
                'wholesale_price': Decimal('3.50'),
                'retail_price': Decimal('4.99'),
                'markup_percentage': Decimal('126.82'),
                'weight': Decimal('0.300'),
                'barcode': '5901234123501',
                'brand': 'Rhodia',
                'manufacturer': 'Clairefontaine',
                'attributes': [
                    ('Pages', '200', 'number'),
                    ('Ruling', 'Lined', 'text'),
                    ('Size', 'A5', 'text'),
                ],
            },
            {
                'sku': 'OFFC-PEN-001',
                'name': 'Ballpoint Pen Pack of 12',
                'description': 'Medium point ballpoint pens, blue ink, pack of 12',
                'category': subcategories['Pens'],
                'status': 'active',
                'purchase_cost': Decimal('3.00'),
                'wholesale_price': Decimal('5.50'),
                'retail_price': Decimal('7.99'),
                'markup_percentage': Decimal('166.33'),
                'weight': Decimal('0.150'),
                'barcode': '5901234123518',
                'brand': 'Bic',
                'manufacturer': 'Bic World',
                'attributes': [
                    ('Ink Color', 'Blue', 'text'),
                    ('Quantity', '12', 'number'),
                    ('Point', 'Medium', 'text'),
                ],
            },
            {
                'sku': 'OFFC-MRK-001',
                'name': 'Highlighter Set 6 Colors',
                'description': 'Chisel tip highlighters, assorted colors, pack of 6',
                'category': subcategories['Markers'],
                'status': 'active',
                'purchase_cost': Decimal('3.50'),
                'wholesale_price': Decimal('5.99'),
                'retail_price': Decimal('8.49'),
                'markup_percentage': Decimal('142.57'),
                'weight': Decimal('0.180'),
                'barcode': '5901234123525',
                'brand': 'Stabilo',
                'manufacturer': 'Schwan-STABILO',
                'attributes': [
                    ('Colors', '6', 'number'),
                    ('Tip', 'Chisel', 'text'),
                ],
            },
            {
                'sku': 'SAFE-PPE-001',
                'name': 'Nitrile Gloves Box of 100',
                'description': 'Disposable nitrile examination gloves, powder-free, size M',
                'category': subcategories['Gloves'],
                'status': 'active',
                'purchase_cost': Decimal('7.50'),
                'wholesale_price': Decimal('11.99'),
                'retail_price': Decimal('14.99'),
                'markup_percentage': Decimal('99.87'),
                'weight': Decimal('0.600'),
                'barcode': '5901234123532',
                'brand': 'Kimberly-Clark',
                'manufacturer': 'Kimberly-Clark Professional',
                'attributes': [
                    ('Size', 'Medium', 'text'),
                    ('Material', 'Nitrile', 'text'),
                    ('Powder-Free', 'Yes', 'boolean'),
                ],
            },
            {
                'sku': 'SAFE-PPE-002',
                'name': 'Safety Glasses Clear Lens',
                'description': 'Impact-resistant safety glasses with anti-fog clear lens',
                'category': subcategories['Safety Glasses'],
                'status': 'active',
                'purchase_cost': Decimal('5.00'),
                'wholesale_price': Decimal('8.99'),
                'retail_price': Decimal('12.99'),
                'markup_percentage': Decimal('159.80'),
                'weight': Decimal('0.035'),
                'barcode': '5901234123549',
                'brand': '3M',
                'manufacturer': '3M Company',
                'attributes': [
                    ('Lens', 'Clear', 'text'),
                    ('Anti-Fog', 'Yes', 'boolean'),
                    ('UV Protection', 'Yes', 'boolean'),
                ],
            },
            {
                'sku': 'SAFE-FAK-001',
                'name': 'First Aid Kit 100-Piece',
                'description': 'Comprehensive first aid kit with 100 pieces for workplace use',
                'category': subcategories['First Aid Kits'],
                'status': 'active',
                'purchase_cost': Decimal('18.00'),
                'wholesale_price': Decimal('27.99'),
                'retail_price': Decimal('34.99'),
                'markup_percentage': Decimal('94.39'),
                'weight': Decimal('0.800'),
                'barcode': '5901234123556',
                'brand': 'Johnson & Johnson',
                'manufacturer': 'Johnson & Johnson Consumer Inc.',
                'attributes': [
                    ('Pieces', '100', 'number'),
                    ('Use', 'Workplace', 'text'),
                ],
            },
            {
                'sku': 'SAFE-BND-001',
                'name': 'Adhesive Bandages Box of 100',
                'description': 'Sterile adhesive bandages, assorted sizes, box of 100',
                'category': subcategories['Bandages'],
                'status': 'draft',
                'purchase_cost': Decimal('4.00'),
                'wholesale_price': Decimal('7.49'),
                'retail_price': Decimal('9.99'),
                'markup_percentage': Decimal('149.75'),
                'weight': Decimal('0.250'),
                'barcode': '5901234123563',
                'brand': 'Band-Aid',
                'manufacturer': 'Johnson & Johnson Consumer Inc.',
                'attributes': [
                    ('Quantity', '100', 'number'),
                    ('Sizes', 'Assorted', 'text'),
                    ('Sterile', 'Yes', 'boolean'),
                ],
            },
        ]

        product_count = 0
        attr_count = 0

        for pdata in products_data:
            attrs = pdata.pop('attributes')
            product, created = Product.objects.get_or_create(
                tenant=tenant,
                sku=pdata['sku'],
                defaults={**pdata, 'is_active': True},
            )
            if created:
                product_count += 1
                for attr_name, attr_value, attr_type in attrs:
                    ProductAttribute.objects.get_or_create(
                        tenant=tenant,
                        product=product,
                        name=attr_name,
                        defaults={
                            'value': attr_value,
                            'attr_type': attr_type,
                            'sort_order': 0,
                        },
                    )
                    attr_count += 1

        self.stdout.write(f'    Created {product_count} products')
        self.stdout.write(f'    Created {attr_count} product attributes')
        self.stdout.write(self.style.SUCCESS(f'  [{tenant.name}] Done!'))
