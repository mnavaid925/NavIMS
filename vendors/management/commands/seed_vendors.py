from decimal import Decimal
from datetime import date, timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import Tenant, User
from vendors.models import Vendor, VendorPerformance, VendorContract, VendorCommunication


class Command(BaseCommand):
    help = 'Seed vendor data (vendors, performance, contracts, communications) for all tenants'

    def add_arguments(self, parser):
        parser.add_argument(
            '--flush',
            action='store_true',
            help='Delete existing vendor data before seeding',
        )

    def handle(self, *args, **options):
        tenants = Tenant.objects.filter(is_active=True)

        if not tenants.exists():
            self.stdout.write(self.style.WARNING(
                'No active tenants found. Run "python manage.py seed" first.'
            ))
            return

        if options['flush']:
            self.stdout.write('Flushing existing vendor data...')
            VendorCommunication.objects.all().delete()
            VendorContract.objects.all().delete()
            VendorPerformance.objects.all().delete()
            Vendor.objects.all().delete()
            self.stdout.write(self.style.SUCCESS('Vendor data flushed.'))

        for tenant in tenants:
            self._seed_tenant(tenant)

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('=' * 60))
        self.stdout.write(self.style.SUCCESS('Vendor seeding complete!'))
        self.stdout.write(self.style.SUCCESS('=' * 60))
        self.stdout.write('')
        self.stdout.write('Login as a tenant admin to see vendor data:')
        self.stdout.write('  admin_acme     / demo123  (Acme Industries)')
        self.stdout.write('  admin_global   / demo123  (Global Supplies Co)')
        self.stdout.write('  admin_techware / demo123  (TechWare Solutions)')
        self.stdout.write('')
        self.stdout.write(self.style.WARNING(
            'Note: Superuser "admin" has no tenant — vendor data '
            'will not appear when logged in as admin.'
        ))

    def _seed_tenant(self, tenant):
        if Vendor.objects.filter(tenant=tenant).exists():
            self.stdout.write(self.style.WARNING(
                f'  [{tenant.name}] Vendor data already exists. '
                f'Use --flush to re-seed.'
            ))
            return

        self.stdout.write(f'\n  Seeding vendors for: {tenant.name}')

        # Get a user for reviewed_by / communicated_by
        admin_user = User.objects.filter(tenant=tenant, is_tenant_admin=True).first()

        # ── Vendors ──
        vendors_data = [
            {
                'company_name': 'Acme Manufacturing Co',
                'contact_person': 'John Smith',
                'email': 'john.smith@acmemfg.com',
                'phone': '+1 (555) 100-1001',
                'website': 'https://www.acmemfg.com',
                'address_line_1': '100 Industrial Blvd',
                'city': 'Detroit',
                'state': 'Michigan',
                'country': 'United States',
                'postal_code': '48201',
                'tax_id': 'US-38-1234567',
                'vendor_type': 'manufacturer',
                'status': 'active',
                'payment_terms': 'net_30',
                'lead_time_days': 14,
                'minimum_order_quantity': 100,
                'notes': 'Primary manufacturer for electronic components.',
            },
            {
                'company_name': 'Global Distribution LLC',
                'contact_person': 'Sarah Chen',
                'email': 'sarah.chen@globaldist.com',
                'phone': '+1 (555) 200-2002',
                'website': 'https://www.globaldist.com',
                'address_line_1': '250 Logistics Way',
                'address_line_2': 'Suite 400',
                'city': 'Chicago',
                'state': 'Illinois',
                'country': 'United States',
                'postal_code': '60601',
                'tax_id': 'US-17-2345678',
                'vendor_type': 'distributor',
                'status': 'active',
                'payment_terms': 'net_60',
                'lead_time_days': 7,
                'minimum_order_quantity': 50,
                'notes': 'Nationwide distribution network with fast shipping.',
            },
            {
                'company_name': 'Premium Wholesale Inc',
                'contact_person': 'Mike Johnson',
                'email': 'mike.j@premwholesale.com',
                'phone': '+1 (555) 300-3003',
                'website': 'https://www.premwholesale.com',
                'address_line_1': '500 Commerce Park',
                'city': 'Dallas',
                'state': 'Texas',
                'country': 'United States',
                'postal_code': '75201',
                'tax_id': 'US-48-3456789',
                'vendor_type': 'wholesaler',
                'status': 'active',
                'payment_terms': 'net_30',
                'lead_time_days': 10,
                'minimum_order_quantity': 200,
                'notes': 'Bulk wholesale pricing with volume discounts.',
            },
            {
                'company_name': 'TechServ Solutions',
                'contact_person': 'Emily Davis',
                'email': 'emily.davis@techserv.io',
                'phone': '+1 (555) 400-4004',
                'website': 'https://www.techserv.io',
                'address_line_1': '75 Innovation Drive',
                'city': 'San Francisco',
                'state': 'California',
                'country': 'United States',
                'postal_code': '94105',
                'tax_id': 'US-06-4567890',
                'vendor_type': 'service_provider',
                'status': 'active',
                'payment_terms': 'net_90',
                'lead_time_days': 3,
                'minimum_order_quantity': 1,
                'notes': 'IT services and consulting. Annual support contracts.',
            },
            {
                'company_name': 'QuickShip Supplies',
                'contact_person': 'Robert Lee',
                'email': 'robert@quickship.com',
                'phone': '+1 (555) 500-5005',
                'address_line_1': '30 Express Lane',
                'city': 'Miami',
                'state': 'Florida',
                'country': 'United States',
                'postal_code': '33101',
                'tax_id': 'US-12-5678901',
                'vendor_type': 'distributor',
                'status': 'pending',
                'payment_terms': 'cod',
                'lead_time_days': 5,
                'minimum_order_quantity': 25,
                'notes': 'New vendor under evaluation. Fast delivery times.',
            },
            {
                'company_name': 'Legacy Parts Corp',
                'contact_person': 'Patricia Brown',
                'email': 'p.brown@legacyparts.com',
                'phone': '+1 (555) 600-6006',
                'address_line_1': '800 Heritage Road',
                'city': 'Cleveland',
                'state': 'Ohio',
                'country': 'United States',
                'postal_code': '44101',
                'tax_id': 'US-39-6789012',
                'vendor_type': 'manufacturer',
                'status': 'inactive',
                'payment_terms': 'net_30',
                'lead_time_days': 21,
                'minimum_order_quantity': 500,
                'notes': 'Legacy supplier. Contract expired. Under review for renewal.',
            },
        ]

        vendors = []
        for vdata in vendors_data:
            vendor, created = Vendor.objects.get_or_create(
                tenant=tenant,
                company_name=vdata['company_name'],
                defaults={**vdata, 'is_active': vdata['status'] != 'inactive'},
            )
            vendors.append(vendor)
        self.stdout.write(f'    Created {len(vendors)} vendors')

        # ── Performance Reviews ──
        today = date.today()
        perf_count = 0
        performance_data = [
            # (vendor_index, days_ago, delivery, quality, compliance, defect_rate, on_time_rate)
            (0, 30, 5, 4, 5, Decimal('1.20'), Decimal('97.50')),
            (0, 90, 4, 5, 4, Decimal('2.00'), Decimal('95.00')),
            (1, 15, 4, 4, 4, Decimal('1.50'), Decimal('96.00')),
            (1, 75, 3, 4, 5, Decimal('2.50'), Decimal('91.00')),
            (2, 20, 5, 5, 5, Decimal('0.50'), Decimal('99.00')),
            (2, 80, 4, 4, 5, Decimal('1.00'), Decimal('97.00')),
            (3, 10, 5, 5, 4, Decimal('0.00'), Decimal('100.00')),
            (3, 60, 5, 4, 4, Decimal('0.50'), Decimal('98.00')),
            (4, 45, 3, 3, 3, Decimal('3.00'), Decimal('88.00')),
            (4, 100, 2, 3, 3, Decimal('5.00'), Decimal('82.00')),
            (5, 120, 3, 2, 3, Decimal('4.50'), Decimal('85.00')),
            (5, 200, 2, 3, 2, Decimal('6.00'), Decimal('78.00')),
        ]

        for vidx, days_ago, dr, qr, cr, defect, ontime in performance_data:
            VendorPerformance.objects.get_or_create(
                tenant=tenant,
                vendor=vendors[vidx],
                review_date=today - timedelta(days=days_ago),
                defaults={
                    'delivery_rating': dr,
                    'quality_rating': qr,
                    'compliance_rating': cr,
                    'defect_rate': defect,
                    'on_time_delivery_rate': ontime,
                    'notes': f'Quarterly performance review for {vendors[vidx].company_name}.',
                    'reviewed_by': admin_user,
                },
            )
            perf_count += 1
        self.stdout.write(f'    Created {perf_count} performance reviews')

        # ── Contracts ──
        contract_count = 0
        contracts_data = [
            # (vendor_index, number, title, start_days_ago, end_days_future, terms, lead, moq, value, status)
            (0, 'CON-001', 'Annual Supply Agreement - Electronics', 180, 185, 'net_30', 14, 100, Decimal('250000.00'), 'active'),
            (0, 'CON-002', 'Q1 Bulk Order Contract', 90, -1, 'net_30', 14, 200, Decimal('75000.00'), 'expired'),
            (1, 'CON-003', 'Distribution Services Agreement', 120, 245, 'net_60', 7, 50, Decimal('180000.00'), 'active'),
            (2, 'CON-004', 'Wholesale Supply Contract 2026', 60, 305, 'net_30', 10, 200, Decimal('320000.00'), 'active'),
            (3, 'CON-005', 'IT Support & Maintenance', 365, 0, 'net_90', 3, 1, Decimal('48000.00'), 'active'),
            (3, 'CON-006', 'Cloud Migration Services', 30, 150, 'net_90', 5, 1, Decimal('95000.00'), 'draft'),
            (4, 'CON-007', 'Trial Supply Agreement', 15, 75, 'cod', 5, 25, Decimal('15000.00'), 'draft'),
            (5, 'CON-008', 'Legacy Parts Supply (Expired)', 400, -35, 'net_30', 21, 500, Decimal('200000.00'), 'expired'),
            (5, 'CON-009', 'Renewal Proposal', 5, 360, 'net_60', 15, 300, Decimal('180000.00'), 'draft'),
        ]

        for vidx, number, title, start_ago, end_future, terms, lead, moq, value, status in contracts_data:
            start = today - timedelta(days=start_ago)
            end = today + timedelta(days=end_future) if end_future > 0 else (today - timedelta(days=abs(end_future)) if end_future < 0 else None)
            VendorContract.objects.get_or_create(
                tenant=tenant,
                contract_number=number,
                defaults={
                    'vendor': vendors[vidx],
                    'title': title,
                    'start_date': start,
                    'end_date': end,
                    'payment_terms': terms,
                    'lead_time_days': lead,
                    'moq': moq,
                    'contract_value': value,
                    'status': status,
                    'notes': f'Contract for {vendors[vidx].company_name}.',
                },
            )
            contract_count += 1
        self.stdout.write(f'    Created {contract_count} contracts')

        # ── Communications ──
        comm_count = 0
        now = timezone.now()
        comms_data = [
            # (vendor_index, type, subject, message, contact, days_ago)
            (0, 'email', 'Initial vendor onboarding', 'Welcome package sent with account setup instructions.', 'John Smith', 150),
            (0, 'meeting', 'Q1 Business Review', 'Discussed Q1 performance metrics and upcoming product roadmap.', 'John Smith', 45),
            (0, 'phone', 'Delivery delay follow-up', 'Called to discuss delayed shipment #SH-2045. Resolved within 48hrs.', 'John Smith', 10),
            (1, 'email', 'Distribution agreement negotiation', 'Sent revised terms for the 2026 distribution agreement.', 'Sarah Chen', 130),
            (1, 'meeting', 'Quarterly performance review', 'In-person meeting at Chicago office. Reviewed KPIs and SLAs.', 'Sarah Chen', 30),
            (2, 'email', 'Pricing update request', 'Requested updated pricing for bulk orders exceeding 500 units.', 'Mike Johnson', 60),
            (2, 'note', 'Internal note: vendor evaluation', 'Premium Wholesale consistently delivers on time. Recommend increasing order volume.', '', 20),
            (2, 'phone', 'Volume discount negotiation', 'Discussed 15% discount for orders over 1000 units. Awaiting confirmation.', 'Mike Johnson', 5),
            (3, 'email', 'Cloud migration kickoff', 'Sent project timeline and requirements document for cloud migration.', 'Emily Davis', 25),
            (3, 'meeting', 'Technical architecture review', 'Reviewed proposed cloud architecture. Approved with minor adjustments.', 'Emily Davis', 15),
            (4, 'email', 'New vendor introduction', 'Initial contact. Requested catalog and pricing information.', 'Robert Lee', 50),
            (4, 'phone', 'Sample order discussion', 'Discussed trial order of 25 units for quality evaluation.', 'Robert Lee', 40),
            (4, 'note', 'Internal: evaluation status', 'Trial order received. Quality acceptable. Pending final approval from procurement.', '', 30),
            (5, 'email', 'Contract renewal discussion', 'Sent renewal terms for review. Awaiting response.', 'Patricia Brown', 10),
            (5, 'note', 'Internal: vendor status review', 'Legacy Parts Corp has been inactive. Evaluating whether to renew or find alternative supplier.', '', 3),
        ]

        for vidx, comm_type, subject, message, contact, days_ago in comms_data:
            VendorCommunication.objects.get_or_create(
                tenant=tenant,
                vendor=vendors[vidx],
                subject=subject,
                defaults={
                    'communication_type': comm_type,
                    'message': message,
                    'contact_person': contact,
                    'communicated_by': admin_user,
                    'communication_date': now - timedelta(days=days_ago),
                },
            )
            comm_count += 1
        self.stdout.write(f'    Created {comm_count} communications')

        self.stdout.write(self.style.SUCCESS(f'  [{tenant.name}] Done!'))
