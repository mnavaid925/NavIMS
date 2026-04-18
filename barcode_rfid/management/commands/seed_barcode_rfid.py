"""Idempotent seed command for the Barcode & RFID Integration module.

Per project rules (CLAUDE.md):
- Safe to run multiple times without --flush
- Skips if data already exists for the tenant
- Prints tenant admin login creds + warns about superuser having no tenant
"""
import random
import secrets
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import Tenant, User
from warehousing.models import Warehouse, Zone

from barcode_rfid.models import (
    LabelTemplate, LabelPrintJob,
    ScannerDevice, ScanEvent,
    RFIDTag, RFIDReader, RFIDReadEvent,
    BatchScanSession, BatchScanItem,
)


class Command(BaseCommand):
    help = 'Seed Barcode & RFID Integration demo data for all tenants'

    def add_arguments(self, parser):
        parser.add_argument('--flush', action='store_true', help='Delete existing barcode_rfid data before seeding')

    def handle(self, *args, **options):
        tenants = Tenant.objects.filter(is_active=True)
        if not tenants.exists():
            self.stdout.write(self.style.WARNING('No active tenants. Run "python manage.py seed" first.'))
            return

        if options['flush']:
            self.stdout.write('Flushing existing barcode & RFID data...')
            BatchScanItem.objects.all().delete()
            BatchScanSession.objects.all().delete()
            RFIDReadEvent.objects.all().delete()
            RFIDReader.objects.all().delete()
            RFIDTag.objects.all().delete()
            ScanEvent.objects.all().delete()
            ScannerDevice.objects.all().delete()
            LabelPrintJob.objects.all().delete()
            LabelTemplate.objects.all().delete()
            self.stdout.write(self.style.SUCCESS('Barcode & RFID data flushed.'))

        for tenant in tenants:
            self._seed_tenant(tenant)

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('Barcode & RFID seeding complete!'))
        self.stdout.write('')
        self.stdout.write('Login as a tenant admin to see the module data:')
        self.stdout.write('  admin_acme / demo123')
        self.stdout.write('  admin_global / demo123')
        self.stdout.write('  admin_techware / demo123')
        self.stdout.write('')
        self.stdout.write(self.style.WARNING(
            "Superuser 'admin' has no tenant — data won't appear when logged in as admin."
        ))

    def _seed_tenant(self, tenant):
        if LabelTemplate.objects.filter(tenant=tenant).exists():
            self.stdout.write(self.style.WARNING(
                f'[{tenant.name}] Barcode & RFID data already exists — skipping. Use --flush to re-seed.'
            ))
            return

        self.stdout.write(f'[{tenant.name}] Seeding…')
        creator = User.objects.filter(tenant=tenant, is_tenant_admin=True).first()
        warehouses = list(Warehouse.objects.filter(tenant=tenant, is_active=True)[:2])
        if not warehouses:
            self.stdout.write(self.style.WARNING(
                f'  No warehouses for {tenant.name} — skipping; run seed_warehousing first.'
            ))
            return

        wh = warehouses[0]
        zones = list(Zone.objects.filter(tenant=tenant, warehouse=wh)[:2])

        # 1. Label Templates (3)
        template_rows = [
            ('LBL-PROD', 'Product Label (CODE128)', 'barcode', 'code128', 'label_medium', 60, 40),
            ('LBL-BIN', 'Bin Label (QR)', 'qr', 'qr', 'label_small', 40, 20),
            ('LBL-SHIP', 'Shipping Label (Mixed)', 'mixed', 'code128', 'label_large', 100, 60),
        ]
        templates = []
        for code, name, ltype, sym, paper, w, h in template_rows:
            obj, _ = LabelTemplate.objects.get_or_create(
                tenant=tenant, code=code,
                defaults=dict(
                    name=name, label_type=ltype, symbology=sym, paper_size=paper,
                    width_mm=w, height_mm=h,
                    includes_name=True, includes_sku=True, is_active=True, created_by=creator,
                ),
            )
            templates.append(obj)

        # 2. Label Print Jobs (2)
        for tpl, tgt, qty, status in [
            (templates[0], 'Widget A — SKU-001', 20, 'printed'),
            (templates[1], 'Bin A-01-01', 5, 'draft'),
        ]:
            existing = LabelPrintJob.objects.filter(tenant=tenant, target_display=tgt, template=tpl).first()
            if existing:
                continue
            job = LabelPrintJob(
                tenant=tenant, template=tpl,
                target_type='product' if 'SKU' in tgt else 'bin',
                target_display=tgt, quantity=qty, status=status,
                created_by=creator,
            )
            if status == 'printed':
                job.printed_at = timezone.now()
                job.printed_by = creator
            job.save()

        # 3. Scanner Devices (3)
        device_rows = [
            ('SCAN-001', 'Receiving Scanner #1', 'handheld', 'Zebra', 'TC25', 'active'),
            ('SCAN-002', 'Picking Scanner #2', 'handheld', 'Honeywell', 'CT40', 'active'),
            ('SCAN-003', 'Shipping Tablet', 'tablet', 'Samsung', 'Tab Active3', 'maintenance'),
        ]
        devices = []
        for code, name, dtype, mfr, model, status in device_rows:
            obj, created = ScannerDevice.objects.get_or_create(
                tenant=tenant, device_code=code,
                defaults=dict(
                    name=name, device_type=dtype, manufacturer=mfr, model_number=model,
                    assigned_warehouse=wh, status=status, assigned_to=creator,
                    battery_level_percent=random.randint(40, 100), is_active=True,
                ),
            )
            devices.append(obj)

        # 4. Scan Events (10)
        scan_types = ['receive', 'pick', 'count', 'lookup', 'transfer']
        for i in range(10):
            ScanEvent.objects.create(
                tenant=tenant,
                device=random.choice(devices),
                user=creator,
                scan_type=random.choice(scan_types),
                barcode_value=f'SKU-{(i+1):03d}',
                symbology='code128',
                resolved_object_type='product',
                resolved_display=f'Demo Product #{i+1}',
                warehouse=wh,
                status='success' if i % 4 != 3 else 'unmatched',
            )

        # 5. RFID Tags (8)
        rfid_rows = [
            ('E20034120123456789ABCDE0', 'passive', 'uhf', 'active', 'pallet'),
            ('E20034120123456789ABCDE1', 'passive', 'uhf', 'active', 'pallet'),
            ('E20034120123456789ABCDE2', 'passive', 'hf', 'unassigned', 'none'),
            ('E20034120123456789ABCDE3', 'active', 'uhf', 'active', 'bin'),
            ('E20034120123456789ABCDE4', 'active', 'uhf', 'inactive', 'bin'),
            ('E20034120123456789ABCDE5', 'passive', 'uhf', 'lost', 'pallet'),
            ('E20034120123456789ABCDE6', 'passive', 'uhf', 'damaged', 'pallet'),
            ('E20034120123456789ABCDE7', 'semi_active', 'uhf', 'retired', 'none'),
        ]
        tags = []
        for epc, ttype, band, status, linked in rfid_rows:
            obj, _ = RFIDTag.objects.get_or_create(
                tenant=tenant, epc_code=epc,
                defaults=dict(
                    tag_type=ttype, frequency_band=band, status=status,
                    linked_object_type=linked, linked_display=f'Pallet P-{random.randint(100, 999)}' if linked == 'pallet' else '',
                    read_count=random.randint(0, 250),
                    battery_voltage=Decimal('3.60') if ttype == 'active' else None,
                ),
            )
            tags.append(obj)

        # 6. RFID Readers (2)
        reader_rows = [
            ('RDR-GATE-01', 'Main Gate Reader', 'fixed_gate', 'online'),
            ('RDR-HAND-01', 'Warehouse Floor Handheld', 'handheld', 'offline'),
        ]
        readers = []
        for code, name, rtype, status in reader_rows:
            obj, _ = RFIDReader.objects.get_or_create(
                tenant=tenant, reader_code=code,
                defaults=dict(
                    name=name, reader_type=rtype, warehouse=wh,
                    zone=zones[0] if zones else None,
                    antenna_count=4 if rtype == 'fixed_gate' else 1,
                    frequency_band='uhf', status=status, is_active=True,
                    ip_address='192.168.1.101' if rtype == 'fixed_gate' else None,
                ),
            )
            readers.append(obj)

        # 7. RFID Read Events (15)
        active_tags = [t for t in tags if t.status in ('active', 'inactive')]
        if active_tags:
            for i in range(15):
                RFIDReadEvent.objects.create(
                    tenant=tenant,
                    tag=random.choice(active_tags),
                    reader=random.choice(readers),
                    signal_strength_dbm=random.randint(-75, -40),
                    read_count_at_event=random.randint(1, 5),
                    direction=random.choice(['in', 'out', 'unknown']),
                    antenna_number=random.randint(1, 4),
                )

        # 8. Batch Scan Sessions (2) + items (5 each)
        for purpose, status, count in [('receiving', 'completed', 5), ('counting', 'active', 3)]:
            session = BatchScanSession(
                tenant=tenant, purpose=purpose,
                device=devices[0] if devices else None,
                user=creator, warehouse=wh,
                zone=zones[0] if zones else None,
                status=status, created_by=creator,
                completed_at=timezone.now() if status == 'completed' else None,
            )
            session.save()
            for j in range(count):
                BatchScanItem.objects.create(
                    tenant=tenant, session=session,
                    scanned_value=f'SKU-{random.randint(1, 20):03d}',
                    symbology='code128',
                    resolution_type='product',
                    resolved_display=f'Demo Product #{j+1}',
                    quantity=Decimal(str(random.randint(1, 5))),
                    is_resolved=True,
                )
            session.total_items_scanned = session.items.count()
            session.save(update_fields=['total_items_scanned', 'updated_at'])

        self.stdout.write(self.style.SUCCESS(
            f'  [{tenant.name}] 3 templates, 2 jobs, 3 devices, 10 scans, 8 tags, 2 readers, 15 reads, 2 sessions seeded.'
        ))
