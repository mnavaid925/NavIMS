from decimal import Decimal
from datetime import date, timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import Tenant, User
from catalog.models import Product
from vendors.models import Vendor
from purchase_orders.models import (
    PurchaseOrder, PurchaseOrderItem, ApprovalRule, PurchaseOrderApproval,
)


class Command(BaseCommand):
    help = 'Seed purchase order data (POs, line items, approval rules) for all tenants'

    def add_arguments(self, parser):
        parser.add_argument(
            '--flush',
            action='store_true',
            help='Delete existing purchase order data before seeding',
        )

    def handle(self, *args, **options):
        tenants = Tenant.objects.filter(is_active=True)

        if not tenants.exists():
            self.stdout.write(self.style.WARNING(
                'No active tenants found. Run "python manage.py seed" first.'
            ))
            return

        if options['flush']:
            self.stdout.write('Flushing existing purchase order data...')
            PurchaseOrderApproval.objects.all().delete()
            PurchaseOrderItem.objects.all().delete()
            PurchaseOrder.objects.all().delete()
            ApprovalRule.objects.all().delete()
            self.stdout.write(self.style.SUCCESS('Purchase order data flushed.'))

        for tenant in tenants:
            self._seed_tenant(tenant)

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('=' * 60))
        self.stdout.write(self.style.SUCCESS('Purchase order seeding complete!'))
        self.stdout.write(self.style.SUCCESS('=' * 60))
        self.stdout.write('')
        self.stdout.write('Login as a tenant admin to see PO data:')
        self.stdout.write('  admin_acme     / demo123  (Acme Industries)')
        self.stdout.write('  admin_global   / demo123  (Global Supplies Co)')
        self.stdout.write('  admin_techware / demo123  (TechWare Solutions)')
        self.stdout.write('')
        self.stdout.write(self.style.WARNING(
            'Note: Superuser "admin" has no tenant — PO data '
            'will not appear when logged in as admin.'
        ))

    def _seed_tenant(self, tenant):
        if PurchaseOrder.objects.filter(tenant=tenant).exists():
            self.stdout.write(self.style.WARNING(
                f'  [{tenant.name}] PO data already exists. '
                f'Use --flush to re-seed.'
            ))
            return

        self.stdout.write(f'\n  Seeding purchase orders for: {tenant.name}')

        admin_user = User.objects.filter(tenant=tenant, is_tenant_admin=True).first()
        vendors = list(Vendor.objects.filter(tenant=tenant, is_active=True)[:4])
        products = list(Product.objects.filter(tenant=tenant, status='active')[:8])

        if not vendors:
            self.stdout.write(self.style.WARNING(
                f'  [{tenant.name}] No vendors found. Run "python manage.py seed_vendors" first.'
            ))
            return

        if not products:
            self.stdout.write(self.style.WARNING(
                f'  [{tenant.name}] No products found. Run "python manage.py seed_catalog" first.'
            ))
            return

        # ── Approval Rules ──
        rules_data = [
            {'name': 'Low Value Orders', 'min_amount': Decimal('0'), 'max_amount': Decimal('1000.00'), 'required_approvals': 1},
            {'name': 'Medium Value Orders', 'min_amount': Decimal('1000.01'), 'max_amount': Decimal('10000.00'), 'required_approvals': 2},
            {'name': 'High Value Orders', 'min_amount': Decimal('10000.01'), 'max_amount': Decimal('999999.99'), 'required_approvals': 3},
        ]

        rules = []
        for rd in rules_data:
            rule = ApprovalRule.objects.create(tenant=tenant, **rd)
            rules.append(rule)
        self.stdout.write(f'    Created {len(rules)} approval rules')

        # ── Purchase Orders ──
        today = date.today()
        po_definitions = [
            {
                'vendor_idx': 0,
                'status': 'draft',
                'order_date': today,
                'expected_delivery_date': today + timedelta(days=14),
                'payment_terms': 'net_30',
                'notes': 'Draft order for office supplies.',
                'items': [
                    {'product_idx': 0, 'quantity': 10, 'unit_price': Decimal('25.00'), 'tax_rate': Decimal('10.00'), 'discount': Decimal('0')},
                    {'product_idx': 1, 'quantity': 5, 'unit_price': Decimal('150.00'), 'tax_rate': Decimal('10.00'), 'discount': Decimal('5.00')},
                ],
            },
            {
                'vendor_idx': 1,
                'status': 'pending_approval',
                'order_date': today - timedelta(days=2),
                'expected_delivery_date': today + timedelta(days=12),
                'payment_terms': 'net_60',
                'notes': 'Awaiting management approval.',
                'items': [
                    {'product_idx': 2, 'quantity': 20, 'unit_price': Decimal('45.00'), 'tax_rate': Decimal('5.00'), 'discount': Decimal('2.00')},
                    {'product_idx': 3, 'quantity': 15, 'unit_price': Decimal('80.00'), 'tax_rate': Decimal('5.00'), 'discount': Decimal('0')},
                    {'product_idx': 0, 'quantity': 50, 'unit_price': Decimal('12.50'), 'tax_rate': Decimal('10.00'), 'discount': Decimal('1.00')},
                ],
            },
            {
                'vendor_idx': 0,
                'status': 'approved',
                'order_date': today - timedelta(days=5),
                'expected_delivery_date': today + timedelta(days=9),
                'payment_terms': 'net_30',
                'notes': 'Approved and ready to send.',
                'items': [
                    {'product_idx': 1, 'quantity': 8, 'unit_price': Decimal('200.00'), 'tax_rate': Decimal('10.00'), 'discount': Decimal('10.00')},
                    {'product_idx': 4 % len(products), 'quantity': 3, 'unit_price': Decimal('500.00'), 'tax_rate': Decimal('10.00'), 'discount': Decimal('0')},
                ],
                'approvals': [{'decision': 'approved', 'notes': 'Looks good, approved.'}],
            },
            {
                'vendor_idx': 2 % len(vendors),
                'status': 'sent',
                'order_date': today - timedelta(days=10),
                'expected_delivery_date': today + timedelta(days=4),
                'payment_terms': 'net_30',
                'notes': 'Sent to vendor on ' + (today - timedelta(days=8)).strftime('%b %d'),
                'items': [
                    {'product_idx': 0, 'quantity': 100, 'unit_price': Decimal('15.00'), 'tax_rate': Decimal('0'), 'discount': Decimal('1.00')},
                    {'product_idx': 2, 'quantity': 50, 'unit_price': Decimal('30.00'), 'tax_rate': Decimal('5.00'), 'discount': Decimal('0')},
                ],
                'approvals': [{'decision': 'approved', 'notes': 'Approved for dispatch.'}],
            },
            {
                'vendor_idx': 1,
                'status': 'partially_received',
                'order_date': today - timedelta(days=20),
                'expected_delivery_date': today - timedelta(days=6),
                'payment_terms': 'net_60',
                'notes': 'Partial shipment received. Awaiting remaining items.',
                'items': [
                    {'product_idx': 3, 'quantity': 30, 'unit_price': Decimal('55.00'), 'tax_rate': Decimal('10.00'), 'discount': Decimal('3.00')},
                    {'product_idx': 5 % len(products), 'quantity': 25, 'unit_price': Decimal('40.00'), 'tax_rate': Decimal('10.00'), 'discount': Decimal('0')},
                ],
                'approvals': [{'decision': 'approved', 'notes': 'Standard approval.'}],
            },
            {
                'vendor_idx': 0,
                'status': 'received',
                'order_date': today - timedelta(days=30),
                'expected_delivery_date': today - timedelta(days=16),
                'payment_terms': 'net_30',
                'notes': 'All items received and verified.',
                'items': [
                    {'product_idx': 1, 'quantity': 12, 'unit_price': Decimal('175.00'), 'tax_rate': Decimal('10.00'), 'discount': Decimal('5.00')},
                ],
                'approvals': [{'decision': 'approved', 'notes': 'Rush order approved.'}],
            },
            {
                'vendor_idx': 3 % len(vendors),
                'status': 'closed',
                'order_date': today - timedelta(days=45),
                'expected_delivery_date': today - timedelta(days=31),
                'payment_terms': 'cod',
                'notes': 'Order completed and closed.',
                'items': [
                    {'product_idx': 0, 'quantity': 200, 'unit_price': Decimal('10.00'), 'tax_rate': Decimal('0'), 'discount': Decimal('0.50')},
                    {'product_idx': 6 % len(products), 'quantity': 75, 'unit_price': Decimal('22.00'), 'tax_rate': Decimal('5.00'), 'discount': Decimal('0')},
                    {'product_idx': 2, 'quantity': 40, 'unit_price': Decimal('35.00'), 'tax_rate': Decimal('10.00'), 'discount': Decimal('2.00')},
                ],
                'approvals': [{'decision': 'approved', 'notes': 'Approved.'}],
            },
            {
                'vendor_idx': 2 % len(vendors),
                'status': 'cancelled',
                'order_date': today - timedelta(days=15),
                'expected_delivery_date': today - timedelta(days=1),
                'payment_terms': 'net_90',
                'notes': 'Cancelled — vendor unable to fulfill.',
                'items': [
                    {'product_idx': 7 % len(products), 'quantity': 5, 'unit_price': Decimal('350.00'), 'tax_rate': Decimal('10.00'), 'discount': Decimal('0')},
                ],
            },
        ]

        po_count = 0
        item_count = 0
        approval_count = 0

        for po_def in po_definitions:
            vendor = vendors[po_def['vendor_idx']]
            po = PurchaseOrder(
                tenant=tenant,
                vendor=vendor,
                order_date=po_def['order_date'],
                expected_delivery_date=po_def.get('expected_delivery_date'),
                payment_terms=po_def['payment_terms'],
                notes=po_def.get('notes', ''),
                created_by=admin_user,
            )
            po.save()  # auto-generates po_number

            # Override status after save (since default is 'draft')
            if po_def['status'] != 'draft':
                PurchaseOrder.objects.filter(pk=po.pk).update(status=po_def['status'])

            # Create line items
            for item_def in po_def['items']:
                product = products[item_def['product_idx']]
                PurchaseOrderItem.objects.create(
                    tenant=tenant,
                    purchase_order=po,
                    product=product,
                    description=product.name,
                    quantity=item_def['quantity'],
                    unit_price=item_def['unit_price'],
                    tax_rate=item_def['tax_rate'],
                    discount=item_def['discount'],
                )
                item_count += 1

            # Create approvals
            if admin_user and 'approvals' in po_def:
                for appr_def in po_def['approvals']:
                    PurchaseOrderApproval.objects.create(
                        tenant=tenant,
                        purchase_order=po,
                        approver=admin_user,
                        decision=appr_def['decision'],
                        notes=appr_def.get('notes', ''),
                    )
                    approval_count += 1

            po_count += 1

        self.stdout.write(f'    Created {po_count} purchase orders')
        self.stdout.write(f'    Created {item_count} line items')
        self.stdout.write(f'    Created {approval_count} approval records')
