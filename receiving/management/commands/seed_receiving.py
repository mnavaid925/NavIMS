from decimal import Decimal
from datetime import date, timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import Tenant, User
from catalog.models import Product
from vendors.models import Vendor
from purchase_orders.models import PurchaseOrder, PurchaseOrderItem
from receiving.models import (
    WarehouseLocation, GoodsReceiptNote, GoodsReceiptNoteItem,
    VendorInvoice, ThreeWayMatch, QualityInspection,
    QualityInspectionItem, PutawayTask,
)


class Command(BaseCommand):
    help = 'Seed receiving & putaway data for all tenants'

    def add_arguments(self, parser):
        parser.add_argument(
            '--flush',
            action='store_true',
            help='Delete existing receiving data before seeding',
        )

    def handle(self, *args, **options):
        tenants = Tenant.objects.filter(is_active=True)

        if not tenants.exists():
            self.stdout.write(self.style.WARNING(
                'No active tenants found. Run "python manage.py seed" first.'
            ))
            return

        if options['flush']:
            self.stdout.write('Flushing existing receiving data...')
            PutawayTask.objects.all().delete()
            QualityInspectionItem.objects.all().delete()
            QualityInspection.objects.all().delete()
            ThreeWayMatch.objects.all().delete()
            VendorInvoice.objects.all().delete()
            GoodsReceiptNoteItem.objects.all().delete()
            GoodsReceiptNote.objects.all().delete()
            WarehouseLocation.objects.all().delete()
            self.stdout.write(self.style.SUCCESS('Receiving data flushed.'))

        for tenant in tenants:
            self._seed_tenant(tenant)

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('=' * 60))
        self.stdout.write(self.style.SUCCESS('Receiving & Putaway seeding complete!'))
        self.stdout.write(self.style.SUCCESS('=' * 60))
        self.stdout.write('')
        self.stdout.write('Login as a tenant admin to see receiving data:')
        self.stdout.write('  admin_acme / demo123')
        self.stdout.write('  admin_global / demo123')
        self.stdout.write('  admin_techware / demo123')
        self.stdout.write('')
        self.stdout.write(self.style.WARNING(
            "Superuser 'admin' has no tenant — data won't appear when logged in as admin"
        ))

    def _seed_tenant(self, tenant):
        self.stdout.write(f'\nSeeding receiving data for tenant: {tenant.name}')

        # Check for existing data
        if WarehouseLocation.objects.filter(tenant=tenant).exists():
            self.stdout.write(self.style.WARNING(
                f'  Receiving data already exists for {tenant.name}. Use --flush to re-seed.'
            ))
            return

        # Get a tenant admin user
        admin_user = User.objects.filter(tenant=tenant, is_tenant_admin=True).first()
        if not admin_user:
            self.stdout.write(self.style.WARNING(f'  No admin user found for {tenant.name}. Skipping.'))
            return

        # Get POs that can receive items (sent or partially_received)
        receivable_pos = PurchaseOrder.objects.filter(
            tenant=tenant, status__in=['sent', 'partially_received'],
        ).select_related('vendor')

        if not receivable_pos.exists():
            self.stdout.write(self.style.WARNING(
                f'  No POs in sent/partially_received status for {tenant.name}. Skipping.'
            ))
            return

        # ── Warehouse Locations ──
        self.stdout.write('  Creating warehouse locations...')
        zone = WarehouseLocation.objects.create(
            tenant=tenant, name='Main Warehouse', code='WH-MAIN',
            location_type='zone', capacity=0, is_active=True,
        )
        aisle_a = WarehouseLocation.objects.create(
            tenant=tenant, name='Aisle A', code='WH-A',
            location_type='aisle', parent=zone, capacity=0, is_active=True,
        )
        aisle_b = WarehouseLocation.objects.create(
            tenant=tenant, name='Aisle B', code='WH-B',
            location_type='aisle', parent=zone, capacity=0, is_active=True,
        )
        bins = []
        bin_data = [
            ('Bin A-01', 'A-01', aisle_a, 500),
            ('Bin A-02', 'A-02', aisle_a, 300),
            ('Bin B-01', 'B-01', aisle_b, 800),
            ('Bin B-02', 'B-02', aisle_b, 1000),
        ]
        for name, code, parent, cap in bin_data:
            b = WarehouseLocation.objects.create(
                tenant=tenant, name=name, code=code,
                location_type='bin', parent=parent,
                capacity=cap, current_quantity=0, is_active=True,
            )
            bins.append(b)
        self.stdout.write(self.style.SUCCESS(f'    Created {3 + len(bins)} locations'))

        # ── GRNs ──
        self.stdout.write('  Creating GRNs...')
        today = date.today()
        grns_created = []

        for i, po in enumerate(receivable_pos[:3]):
            po_items = list(po.items.all().select_related('product'))
            if not po_items:
                continue

            statuses = ['draft', 'completed', 'completed']
            status = statuses[i % len(statuses)]

            grn = GoodsReceiptNote(
                tenant=tenant,
                purchase_order=po,
                received_date=today - timedelta(days=10 - i * 3),
                status=status,
                delivery_note_number=f'DN-{1000 + i}',
                notes=f'Received shipment from {po.vendor.company_name}',
                received_by=admin_user,
                created_by=admin_user,
            )
            grn.save()

            for j, po_item in enumerate(po_items):
                qty = po_item.quantity if status == 'completed' else max(1, po_item.quantity // 2)
                GoodsReceiptNoteItem.objects.create(
                    tenant=tenant,
                    grn=grn,
                    po_item=po_item,
                    product=po_item.product,
                    quantity_received=qty,
                    sort_order=j,
                )

            grns_created.append(grn)

        self.stdout.write(self.style.SUCCESS(f'    Created {len(grns_created)} GRNs'))

        # ── Vendor Invoices ──
        self.stdout.write('  Creating vendor invoices...')
        invoices_created = []
        completed_grns = [g for g in grns_created if g.status == 'completed']

        for i, grn in enumerate(completed_grns[:2]):
            po = grn.purchase_order
            inv_status = ['pending_match', 'matched'][i % 2]
            invoice = VendorInvoice(
                tenant=tenant,
                invoice_number=f'VINV-{2000 + i}',
                vendor=po.vendor,
                purchase_order=po,
                invoice_date=today - timedelta(days=5 - i),
                due_date=today + timedelta(days=25 + i * 5),
                subtotal=po.subtotal,
                tax_amount=po.tax_total,
                total_amount=po.grand_total,
                status=inv_status,
                notes=f'Invoice for PO {po.po_number}',
                created_by=admin_user,
            )
            invoice.save()
            invoices_created.append(invoice)

        self.stdout.write(self.style.SUCCESS(f'    Created {len(invoices_created)} vendor invoices'))

        # ── Three-Way Matches ──
        self.stdout.write('  Creating three-way matches...')
        matches_created = 0
        for i, (grn, inv) in enumerate(zip(completed_grns[:2], invoices_created[:2])):
            if grn.purchase_order_id == inv.purchase_order_id:
                match = ThreeWayMatch(
                    tenant=tenant,
                    purchase_order=grn.purchase_order,
                    grn=grn,
                    vendor_invoice=inv,
                    created_by=admin_user,
                )
                match.save()
                match.perform_match()
                matches_created += 1

        self.stdout.write(self.style.SUCCESS(f'    Created {matches_created} three-way matches'))

        # ── Quality Inspections ──
        self.stdout.write('  Creating quality inspections...')
        inspections_created = 0
        for i, grn in enumerate(completed_grns[:2]):
            insp_status = 'completed'
            inspection = QualityInspection(
                tenant=tenant,
                grn=grn,
                status=insp_status,
                inspector=admin_user,
                inspection_date=grn.received_date + timedelta(days=1),
                notes=f'Quality check for {grn.grn_number}',
                created_by=admin_user,
            )
            inspection.save()

            for grn_item in grn.items.all():
                qty = grn_item.quantity_received
                # First inspection: all accepted. Second: some rejected
                if i == 0:
                    accepted, rejected, quarantined = qty, 0, 0
                    decision = 'accepted'
                else:
                    rejected = max(1, qty // 5)
                    accepted = qty - rejected
                    quarantined = 0
                    decision = 'accepted' if rejected == 0 else 'rejected'

                QualityInspectionItem.objects.create(
                    tenant=tenant,
                    inspection=inspection,
                    grn_item=grn_item,
                    product=grn_item.product,
                    quantity_inspected=qty,
                    quantity_accepted=accepted,
                    quantity_rejected=rejected,
                    quantity_quarantined=quarantined,
                    decision=decision,
                )
            inspections_created += 1

        self.stdout.write(self.style.SUCCESS(f'    Created {inspections_created} quality inspections'))

        # ── Putaway Tasks ──
        self.stdout.write('  Creating putaway tasks...')
        tasks_created = 0
        task_statuses = ['pending', 'assigned', 'in_progress', 'completed']

        for grn in completed_grns[:2]:
            for j, grn_item in enumerate(grn.items.all()):
                status = task_statuses[j % len(task_statuses)]
                suggested_bin = bins[j % len(bins)]
                assigned_bin = suggested_bin if status in ('assigned', 'in_progress', 'completed') else None

                task = PutawayTask(
                    tenant=tenant,
                    grn=grn,
                    grn_item=grn_item,
                    product=grn_item.product,
                    quantity=grn_item.quantity_received,
                    suggested_location=suggested_bin,
                    assigned_location=assigned_bin,
                    status=status,
                    assigned_to=admin_user if status != 'pending' else None,
                    completed_at=timezone.now() if status == 'completed' else None,
                    notes=f'Put away {grn_item.product.name}',
                    created_by=admin_user,
                )
                task.save()

                # Update bin quantity for completed tasks
                if status == 'completed' and assigned_bin:
                    assigned_bin.current_quantity += grn_item.quantity_received
                    assigned_bin.save()

                tasks_created += 1

        self.stdout.write(self.style.SUCCESS(f'    Created {tasks_created} putaway tasks'))

        self.stdout.write(self.style.SUCCESS(f'  Done for {tenant.name}!'))
