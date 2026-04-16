import calendar
import random
from datetime import date, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import Tenant, User
from catalog.models import Product, Category
from warehousing.models import Warehouse
from inventory.models import StockLevel
from forecasting.models import (
    DemandForecast, DemandForecastLine,
    ReorderPoint, ReorderAlert,
    SafetyStock,
    SeasonalityProfile, SeasonalityPeriod,
)


MONTH_LABELS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']


class Command(BaseCommand):
    help = 'Seed Inventory Forecasting & Planning data for all tenants'

    def add_arguments(self, parser):
        parser.add_argument('--flush', action='store_true', help='Delete existing forecasting data before seeding')

    def handle(self, *args, **options):
        tenants = Tenant.objects.filter(is_active=True)
        if not tenants.exists():
            self.stdout.write(self.style.WARNING('No active tenants. Run "python manage.py seed" first.'))
            return

        if options['flush']:
            self.stdout.write('Flushing existing forecasting data...')
            ReorderAlert.objects.all().delete()
            ReorderPoint.objects.all().delete()
            SafetyStock.objects.all().delete()
            DemandForecastLine.objects.all().delete()
            DemandForecast.objects.all().delete()
            SeasonalityPeriod.objects.all().delete()
            SeasonalityProfile.objects.all().delete()
            self.stdout.write(self.style.SUCCESS('Forecasting data flushed.'))

        for tenant in tenants:
            self._seed_tenant(tenant)

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('Forecasting seeding complete!'))
        self.stdout.write('')
        self.stdout.write('Login as a tenant admin to see forecasting data:')
        self.stdout.write('  admin_acme / demo123')
        self.stdout.write('  admin_global / demo123')
        self.stdout.write('  admin_techware / demo123')
        self.stdout.write('')
        self.stdout.write(self.style.WARNING(
            "Superuser 'admin' has no tenant — data won't appear when logged in as admin."
        ))

    def _seed_tenant(self, tenant):
        if DemandForecast.objects.filter(tenant=tenant).exists():
            self.stdout.write(f'  [{tenant.name}] Forecasting data already exists. Use --flush to re-seed.')
            return

        self.stdout.write(f'  [{tenant.name}] Seeding forecasting data...')

        warehouses = list(Warehouse.objects.filter(tenant=tenant, is_active=True)[:2])
        products = list(Product.objects.filter(tenant=tenant, is_active=True)[:6])
        users = list(User.objects.filter(tenant=tenant)[:2])
        categories = list(Category.objects.filter(tenant=tenant)[:3])
        stock_levels = list(StockLevel.objects.filter(tenant=tenant).select_related('product', 'warehouse'))

        if not warehouses or not products:
            self.stdout.write(f'  [{tenant.name}] Missing warehouses or products. Skipping.')
            return

        created_by = users[0] if users else None
        today = timezone.now().date()
        now = timezone.now()

        # ── Seasonality profiles (2 per tenant) ────────────────────
        summer_profile = SeasonalityProfile.objects.create(
            tenant=tenant,
            name='Summer Peak (Jun–Aug)',
            description='Seasonal spike during summer months for outdoor / seasonal products.',
            category=categories[0] if categories else None,
            period_type='month',
            is_active=True,
            created_by=created_by,
        )
        summer_multipliers = {
            1: Decimal('0.85'), 2: Decimal('0.90'), 3: Decimal('0.95'),
            4: Decimal('1.00'), 5: Decimal('1.10'), 6: Decimal('1.35'),
            7: Decimal('1.50'), 8: Decimal('1.30'), 9: Decimal('1.05'),
            10: Decimal('0.95'), 11: Decimal('0.90'), 12: Decimal('0.85'),
        }
        for m in range(1, 13):
            SeasonalityPeriod.objects.create(
                tenant=tenant, profile=summer_profile,
                period_number=m, period_label=MONTH_LABELS[m - 1],
                demand_multiplier=summer_multipliers[m],
            )

        holiday_profile = SeasonalityProfile.objects.create(
            tenant=tenant,
            name='Holiday Season (Nov–Dec)',
            description='Q4 holiday surge for gifting / retail products.',
            category=categories[1] if len(categories) > 1 else None,
            period_type='quarter',
            is_active=True,
            created_by=created_by,
        )
        quarter_multipliers = {1: Decimal('0.90'), 2: Decimal('0.95'), 3: Decimal('1.05'), 4: Decimal('1.40')}
        for q in range(1, 5):
            SeasonalityPeriod.objects.create(
                tenant=tenant, profile=holiday_profile,
                period_number=q, period_label=f'Q{q}',
                demand_multiplier=quarter_multipliers[q],
            )

        # ── Safety stock configs (4 per tenant) ────────────────────
        safety_stocks = []
        ss_methods = [
            ('statistical', Decimal('0.95')),
            ('statistical', Decimal('0.99')),
            ('fixed', Decimal('0.90')),
            ('percentage', Decimal('0.95')),
        ]
        for i, product in enumerate(products[:4]):
            method, sl = ss_methods[i]
            wh = warehouses[i % len(warehouses)]
            avg_demand = Decimal(random.randint(5, 25))
            demand_sd = avg_demand / Decimal('3')
            ss = SafetyStock(
                tenant=tenant,
                product=product,
                warehouse=wh,
                method=method,
                service_level=sl,
                avg_demand=avg_demand,
                demand_std_dev=demand_sd,
                avg_lead_time_days=Decimal(random.randint(5, 15)),
                lead_time_std_dev=Decimal('1.50'),
                fixed_qty=random.randint(20, 50),
                percentage=Decimal('25.00'),
                calculated_at=now,
            )
            ss.recalc()
            ss.save()
            safety_stocks.append(ss)

        # ── Reorder points (5 per tenant) ──────────────────────────
        reorder_points = []
        for i, product in enumerate(products[:5]):
            wh = warehouses[i % len(warehouses)]
            matching_ss = next(
                (s for s in safety_stocks if s.product_id == product.id and s.warehouse_id == wh.id),
                None,
            )
            safety_qty = matching_ss.safety_stock_qty if matching_ss else random.randint(10, 30)
            avg_daily = Decimal(random.randint(3, 15))
            lead_days = random.randint(5, 14)
            rop = ReorderPoint(
                tenant=tenant,
                product=product,
                warehouse=wh,
                avg_daily_usage=avg_daily,
                lead_time_days=lead_days,
                safety_stock_qty=safety_qty,
                min_qty=safety_qty,
                max_qty=int(avg_daily * lead_days * 3) + safety_qty,
                reorder_qty=int(avg_daily * lead_days * 2),
                is_active=True,
                last_calculated_at=now,
                notes='Seeded demo ROP.',
            )
            rop.recalc_rop()
            rop.save()
            reorder_points.append(rop)

        # ── Reorder alerts (3 per tenant based on current stock) ───
        alerts_created = 0
        for rop in reorder_points:
            stock = next(
                (s for s in stock_levels if s.product_id == rop.product_id and s.warehouse_id == rop.warehouse_id),
                None,
            )
            current = (stock.on_hand or 0) - (stock.allocated or 0) if stock else 0

            if alerts_created < 3 and current <= rop.rop_qty + 10:
                ReorderAlert.objects.create(
                    tenant=tenant,
                    rop=rop,
                    product=rop.product,
                    warehouse=rop.warehouse,
                    current_qty=current,
                    rop_qty=rop.rop_qty,
                    suggested_order_qty=max(rop.reorder_qty, rop.max_qty - current),
                    status=['new', 'acknowledged', 'ordered'][alerts_created % 3],
                    notes='Auto-generated by seeder.',
                )
                alerts_created += 1

        # ── Demand forecasts (3 per tenant across methods) ─────────
        forecast_configs = [
            ('Monthly demand — moving average', 'moving_avg', 'monthly', 6, 3, None),
            ('Quarterly seasonal forecast', 'seasonal', 'quarterly', 4, 2, holiday_profile),
            ('Linear trend projection', 'linear_regression', 'monthly', 8, 4, None),
        ]
        for i, (name, method, period_type, hist, future, profile) in enumerate(forecast_configs):
            product = products[i % len(products)]
            wh = warehouses[i % len(warehouses)]
            forecast = DemandForecast.objects.create(
                tenant=tenant,
                name=name,
                product=product,
                warehouse=wh,
                method=method,
                period_type=period_type,
                history_periods=hist,
                forecast_periods=future,
                seasonality_profile=profile,
                confidence_pct=Decimal(random.choice(['75.00', '80.00', '85.00', '90.00'])),
                status='approved' if i == 0 else 'draft',
                created_by=created_by,
                generated_at=now,
                notes='Seeded demo forecast.',
            )
            self._generate_demo_lines(tenant, forecast, today)

        self.stdout.write(f'  [{tenant.name}] Created {len(reorder_points)} ROPs, {alerts_created} alerts, {len(safety_stocks)} safety stocks, 2 seasonality profiles, 3 forecasts.')

    def _generate_demo_lines(self, tenant, forecast, today):
        """Populate forecast lines with synthetic historical + projected data."""
        period_type = forecast.period_type
        base = random.randint(50, 200)
        history_values = []

        # Build history
        for i in range(forecast.history_periods, 0, -1):
            period_index = -i
            start, end, label = self._period_bounds(today, period_index, period_type)
            qty = max(0, base + random.randint(-20, 20))
            history_values.append(qty)
            DemandForecastLine.objects.create(
                tenant=tenant,
                forecast=forecast,
                period_index=period_index,
                period_label=label,
                period_start_date=start,
                period_end_date=end,
                historical_qty=qty,
            )

        # Simple projection based on method
        if forecast.method == 'linear_regression' and len(history_values) >= 2:
            xs = list(range(len(history_values)))
            mean_x = sum(xs) / len(xs)
            mean_y = sum(history_values) / len(history_values)
            num = sum((xs[i] - mean_x) * (history_values[i] - mean_y) for i in range(len(xs)))
            den = sum((xs[i] - mean_x) ** 2 for i in range(len(xs)))
            slope = num / den if den else 0
            intercept = mean_y - slope * mean_x
            forecast_fn = lambda k: max(0, int(round(intercept + slope * (len(history_values) - 1 + k))))
        else:
            avg = sum(history_values) // max(1, len(history_values))
            forecast_fn = lambda k: avg

        for k in range(1, forecast.forecast_periods + 1):
            start, end, label = self._period_bounds(today, k, period_type)
            val = forecast_fn(k)
            adjusted = val
            if forecast.seasonality_profile:
                mult = float(forecast.seasonality_profile.multiplier_for_date(start))
                adjusted = int(round(val * mult))
            DemandForecastLine.objects.create(
                tenant=tenant,
                forecast=forecast,
                period_index=k - 1,
                period_label=label,
                period_start_date=start,
                period_end_date=end,
                forecast_qty=val,
                adjusted_qty=adjusted,
            )

    def _period_bounds(self, reference_date, period_index, period_type):
        if period_type == 'weekly':
            start = reference_date - timedelta(days=reference_date.weekday())
            start = start + timedelta(weeks=period_index)
            end = start + timedelta(days=6)
            label = f"W{start.isocalendar()[1]:02d}-{start.year}"
            return start, end, label

        if period_type == 'quarterly':
            q = (reference_date.month - 1) // 3
            base_year = reference_date.year
            target_q = q + period_index
            year_offset, target_q = divmod(target_q, 4)
            year = base_year + year_offset
            start_month = target_q * 3 + 1
            start = date(year, start_month, 1)
            end_month = start_month + 2
            end_day = calendar.monthrange(year, end_month)[1]
            end = date(year, end_month, end_day)
            label = f"Q{target_q + 1} {year}"
            return start, end, label

        # monthly
        base_year = reference_date.year
        base_month = reference_date.month
        total_months = base_month - 1 + period_index
        year_offset, month_idx = divmod(total_months, 12)
        year = base_year + year_offset
        month = month_idx + 1
        start = date(year, month, 1)
        end = date(year, month, calendar.monthrange(year, month)[1])
        label = start.strftime('%b %Y')
        return start, end, label
