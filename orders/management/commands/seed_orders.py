import random
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import Tenant, User
from catalog.models import Product
from warehousing.models import Warehouse
from orders.models import (
    Carrier, ShippingRate, SalesOrder, SalesOrderItem,
    WavePlan, WaveOrderAssignment, PickList, PickListItem,
    PackingList, Shipment, ShipmentTracking,
)


class Command(BaseCommand):
    help = 'Seed order management & fulfillment data for all tenants'

    def add_arguments(self, parser):
        parser.add_argument(
            '--flush',
            action='store_true',
            help='Delete existing orders data before seeding',
        )

    def handle(self, *args, **options):
        tenants = Tenant.objects.filter(is_active=True)
        if not tenants.exists():
            self.stdout.write(self.style.WARNING(
                'No active tenants found. Run "python manage.py seed" first.'
            ))
            return

        if options['flush']:
            self.stdout.write('Flushing existing orders data...')
            ShipmentTracking.objects.all().delete()
            Shipment.objects.all().delete()
            PackingList.objects.all().delete()
            PickListItem.objects.all().delete()
            PickList.objects.all().delete()
            WaveOrderAssignment.objects.all().delete()
            WavePlan.objects.all().delete()
            SalesOrderItem.objects.all().delete()
            SalesOrder.objects.all().delete()
            ShippingRate.objects.all().delete()
            Carrier.objects.all().delete()
            self.stdout.write(self.style.SUCCESS('Orders data flushed.'))

        for tenant in tenants:
            self._seed_tenant(tenant)

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('Order management seeding complete!'))
        self.stdout.write('')
        self.stdout.write('Login as a tenant admin to see order data:')
        self.stdout.write('  admin_acme / demo123')
        self.stdout.write('  admin_global / demo123')
        self.stdout.write('  admin_techware / demo123')
        self.stdout.write('')
        self.stdout.write(self.style.WARNING(
            "Superuser 'admin' has no tenant — data won't appear when logged in as admin."
        ))

    def _seed_tenant(self, tenant):
        if SalesOrder.objects.filter(tenant=tenant).exists():
            self.stdout.write(f'  [{tenant.name}] Orders data already exists. Use --flush to re-seed.')
            return

        self.stdout.write(f'  [{tenant.name}] Seeding orders data...')

        products = list(Product.objects.filter(tenant=tenant, is_active=True)[:8])
        warehouses = list(Warehouse.objects.filter(tenant=tenant, is_active=True)[:2])
        users = list(User.objects.filter(tenant=tenant)[:3])

        if not products or not warehouses or not users:
            self.stdout.write(f'  [{tenant.name}] Missing products, warehouses, or users. Skipping.')
            return

        admin_user = users[0]
        now = timezone.now()

        # ── Carriers ──
        carriers_data = [
            ('FedEx', 'FEDEX', 'support@fedex.com', '+1-800-463-3339'),
            ('UPS', 'UPS', 'support@ups.com', '+1-800-742-5877'),
            ('DHL Express', 'DHL', 'support@dhl.com', '+1-800-225-5345'),
            ('USPS', 'USPS', 'support@usps.com', '+1-800-275-8777'),
        ]
        carriers = []
        for name, code, email, phone in carriers_data:
            carrier, _ = Carrier.objects.get_or_create(
                tenant=tenant, code=code,
                defaults={
                    'name': name,
                    'contact_email': email,
                    'contact_phone': phone,
                    'is_active': True,
                },
            )
            carriers.append(carrier)

        # ── Shipping Rates ──
        rates_data = [
            (carriers[0], 'Ground', Decimal('9.99'), Decimal('0.50'), 5),
            (carriers[0], 'Express', Decimal('19.99'), Decimal('1.00'), 2),
            (carriers[0], 'Overnight', Decimal('39.99'), Decimal('2.00'), 1),
            (carriers[1], 'Ground', Decimal('8.99'), Decimal('0.45'), 6),
            (carriers[1], '2-Day Air', Decimal('24.99'), Decimal('1.50'), 2),
            (carriers[2], 'Express Worldwide', Decimal('49.99'), Decimal('3.00'), 3),
        ]
        for carrier, service, base, per_kg, days in rates_data:
            ShippingRate.objects.get_or_create(
                tenant=tenant, carrier=carrier, service_level=service,
                defaults={
                    'base_cost': base,
                    'cost_per_kg': per_kg,
                    'estimated_transit_days': days,
                    'is_active': True,
                },
            )

        # ── Sales Orders ──
        customers = [
            ('John Smith', 'john.smith@example.com', '+1-555-0101', '123 Main St, New York, NY 10001'),
            ('Jane Doe', 'jane.doe@example.com', '+1-555-0102', '456 Oak Ave, Los Angeles, CA 90001'),
            ('Acme Corp', 'orders@acmecorp.com', '+1-555-0103', '789 Industry Blvd, Chicago, IL 60601'),
            ('Tech Solutions', 'orders@techsol.com', '+1-555-0104', '321 Tech Park, San Jose, CA 95101'),
            ('Retail World', 'buying@retailworld.com', '+1-555-0105', '654 Commerce St, Dallas, TX 75201'),
            ('Global Imports', 'orders@globalimports.com', '+1-555-0106', '987 Harbor Rd, Miami, FL 33101'),
        ]

        order_configs = [
            # (status, days_ago, priority, customer_idx, product_indices)
            ('draft', 1, 'normal', 0, [0, 1]),
            ('confirmed', 3, 'high', 1, [2, 3]),
            ('in_fulfillment', 5, 'normal', 2, [0, 2, 4]),
            ('picked', 7, 'urgent', 3, [1, 3]),
            ('packed', 9, 'normal', 4, [0, 1, 5]),
            ('shipped', 12, 'high', 5, [2, 4]),
            ('delivered', 20, 'normal', 0, [3, 5, 6]),
            ('cancelled', 2, 'low', 1, [0]),
        ]

        sales_orders = []
        warehouse = warehouses[0]

        for i, (status, days_ago, priority, cust_idx, prod_indices) in enumerate(order_configs):
            cust = customers[cust_idx]
            so = SalesOrder(tenant=tenant)
            so.status = status
            so.priority = priority
            so.customer_name = cust[0]
            so.customer_email = cust[1]
            so.customer_phone = cust[2]
            so.shipping_address = cust[3]
            so.billing_address = cust[3]
            so.order_date = (now - timedelta(days=days_ago)).date()
            so.required_date = (now + timedelta(days=14 - days_ago)).date()
            so.warehouse = warehouse
            so.created_by = admin_user
            so.save()
            sales_orders.append(so)

            for j, pidx in enumerate(prod_indices):
                product = products[pidx % len(products)]
                SalesOrderItem.objects.create(
                    tenant=tenant,
                    sales_order=so,
                    product=product,
                    description=f'{product.name} for order {so.order_number}',
                    quantity=random.randint(1, 10),
                    unit_price=product.retail_price if hasattr(product, 'retail_price') and product.retail_price else Decimal('25.00'),
                    tax_rate=Decimal('10.00'),
                    discount=Decimal('0.00'),
                    sort_order=j,
                )

        self.stdout.write(f'    Created {len(sales_orders)} sales orders with line items')

        # ── Wave Plan ──
        wave = WavePlan(tenant=tenant)
        wave.warehouse = warehouse
        wave.priority = 'high'
        wave.status = 'completed'
        wave.order_date_from = (now - timedelta(days=15)).date()
        wave.order_date_to = (now - timedelta(days=5)).date()
        wave.created_by = admin_user
        wave.released_at = now - timedelta(days=8)
        wave.completed_at = now - timedelta(days=6)
        wave.save()

        # Assign confirmed+ orders to wave
        for so in sales_orders[2:6]:  # in_fulfillment, picked, packed, shipped
            WaveOrderAssignment.objects.create(
                tenant=tenant, wave_plan=wave, sales_order=so,
            )

        self.stdout.write(f'    Created 1 wave plan with 4 orders')

        # ── Pick Lists ──
        pick_list_count = 0
        for so in sales_orders[2:7]:  # in_fulfillment through delivered
            if so.status in ('draft', 'confirmed', 'cancelled'):
                continue
            pl = PickList(tenant=tenant)
            pl.sales_order = so
            pl.warehouse = warehouse
            pl.created_by = admin_user

            if so.status in ('in_fulfillment',):
                pl.status = 'in_progress'
                pl.assigned_to = users[1] if len(users) > 1 else admin_user
                pl.started_at = now - timedelta(days=3)
            else:
                pl.status = 'completed'
                pl.assigned_to = users[1] if len(users) > 1 else admin_user
                pl.started_at = now - timedelta(days=5)
                pl.completed_at = now - timedelta(days=4)

            if wave:
                pl.wave_plan = wave
            pl.save()

            for item in so.items.all():
                PickListItem.objects.create(
                    tenant=tenant,
                    pick_list=pl,
                    product=item.product,
                    ordered_quantity=item.quantity,
                    picked_quantity=item.quantity if pl.status == 'completed' else random.randint(0, item.quantity),
                )
            pick_list_count += 1

        self.stdout.write(f'    Created {pick_list_count} pick lists with items')

        # ── Packing Lists ──
        packing_count = 0
        for so in sales_orders[4:7]:  # packed, shipped, delivered
            pls = so.pick_lists.filter(status='completed')
            if not pls.exists():
                continue
            pl = pls.first()
            packing = PackingList(tenant=tenant)
            packing.pick_list = pl
            packing.sales_order = so
            packing.status = 'completed'
            packing.packaging_type = random.choice(['box', 'pallet', 'crate'])
            packing.total_weight = Decimal(str(round(random.uniform(1.0, 50.0), 2)))
            packing.length = Decimal(str(round(random.uniform(10.0, 100.0), 2)))
            packing.width = Decimal(str(round(random.uniform(10.0, 80.0), 2)))
            packing.height = Decimal(str(round(random.uniform(5.0, 60.0), 2)))
            packing.packed_by = admin_user
            packing.packed_at = now - timedelta(days=3)
            packing.save()
            packing_count += 1

        self.stdout.write(f'    Created {packing_count} packing lists')

        # ── Shipments ──
        shipment_count = 0
        for so in sales_orders[5:7]:  # shipped, delivered
            carrier = random.choice(carriers)
            sh = Shipment(tenant=tenant)
            sh.sales_order = so
            sh.carrier = carrier
            sh.service_level = 'Ground'
            sh.tracking_number = f'TRK{random.randint(100000000, 999999999)}'
            sh.shipping_cost = Decimal(str(round(random.uniform(10.0, 60.0), 2)))
            sh.shipped_by = admin_user
            sh.shipped_date = now - timedelta(days=10)
            sh.estimated_delivery_date = (now + timedelta(days=5)).date()

            packing = so.packing_lists.first()
            if packing:
                sh.packing_list = packing

            if so.status == 'delivered':
                sh.status = 'delivered'
                sh.actual_delivery_date = (now - timedelta(days=2)).date()
            else:
                sh.status = 'dispatched'

            sh.save()
            shipment_count += 1

            # Add tracking events
            events = [
                ('Package picked up', carrier.name + ' facility', now - timedelta(days=10)),
                ('In transit to sorting facility', 'Regional Hub', now - timedelta(days=8)),
                ('Out for delivery', so.shipping_address.split(',')[0] if so.shipping_address else 'Local', now - timedelta(days=3)),
            ]
            if so.status == 'delivered':
                events.append(('Delivered', so.shipping_address.split(',')[0] if so.shipping_address else 'Destination', now - timedelta(days=2)))

            for evt_status, location, evt_date in events:
                ShipmentTracking.objects.create(
                    tenant=tenant,
                    shipment=sh,
                    status=evt_status,
                    location=location,
                    description=f'{evt_status} — {sh.tracking_number}',
                    event_date=evt_date,
                )

        self.stdout.write(f'    Created {shipment_count} shipments with tracking events')
        self.stdout.write(self.style.SUCCESS(f'  [{tenant.name}] Orders seeding complete!'))
