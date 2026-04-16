"""Form-level negative coverage — regression guards for every D-01..D-07 fix."""
import pytest
from datetime import date, timedelta
from decimal import Decimal
from django.core.files.uploadedfile import SimpleUploadedFile

from vendors.forms import (
    VendorForm,
    VendorPerformanceForm,
    VendorContractForm,
)


def _base_vendor_data(**overrides):
    data = {
        'company_name': 'New Vendor',
        'vendor_type': 'distributor',
        'status': 'active',
        'payment_terms': 'net_30',
        'lead_time_days': 0,
        'minimum_order_quantity': 1,
        'is_active': 'on',
    }
    data.update(overrides)
    return data


def _base_performance_data(vendor, **overrides):
    data = {
        'vendor': vendor.pk,
        'review_date': date.today().isoformat(),
        'delivery_rating': 5, 'quality_rating': 5, 'compliance_rating': 5,
        'defect_rate': '0', 'on_time_delivery_rate': '100',
    }
    data.update(overrides)
    return data


def _base_contract_data(vendor, **overrides):
    data = {
        'vendor': vendor.pk,
        'contract_number': 'CON-BAR',
        'title': 'Test',
        'start_date': date.today().isoformat(),
        'end_date': '',
        'payment_terms': 'net_30',
        'lead_time_days': 0, 'moq': 1,
        'contract_value': '0.00',
        'status': 'draft',
    }
    data.update(overrides)
    return data


@pytest.mark.django_db
class TestVendorFormDuplicate:
    """D-01 regression."""
    def test_duplicate_company_name_same_tenant_form_error(self, tenant, vendor):
        form = VendorForm(data=_base_vendor_data(company_name='Acme Corp'), tenant=tenant)
        assert form.is_valid() is False
        assert 'company_name' in form.errors

    def test_duplicate_company_name_case_insensitive(self, tenant, vendor):
        form = VendorForm(data=_base_vendor_data(company_name='ACME CORP'), tenant=tenant)
        assert form.is_valid() is False
        assert 'company_name' in form.errors

    def test_edit_form_allows_keeping_own_name(self, tenant, vendor):
        form = VendorForm(
            data=_base_vendor_data(company_name='Acme Corp'),
            instance=vendor,
            tenant=tenant,
        )
        assert form.is_valid() is True, form.errors

    def test_same_name_across_tenants_allowed(self, other_tenant, vendor):
        form = VendorForm(data=_base_vendor_data(company_name='Acme Corp'), tenant=other_tenant)
        assert form.is_valid() is True, form.errors

    def test_javascript_url_rejected(self, tenant):
        form = VendorForm(
            data=_base_vendor_data(website='javascript:alert(1)'),
            tenant=tenant,
        )
        assert form.is_valid() is False
        assert 'website' in form.errors


@pytest.mark.django_db
class TestPerformanceFormBoundaries:

    @pytest.mark.parametrize('field', ['delivery_rating', 'quality_rating', 'compliance_rating'])
    def test_rating_zero_rejected(self, tenant, vendor, field):
        data = _base_performance_data(vendor, **{field: 0})
        form = VendorPerformanceForm(data=data, tenant=tenant)
        assert form.is_valid() is False
        assert field in form.errors

    @pytest.mark.parametrize('field', ['delivery_rating', 'quality_rating', 'compliance_rating'])
    def test_rating_six_rejected(self, tenant, vendor, field):
        data = _base_performance_data(vendor, **{field: 6})
        form = VendorPerformanceForm(data=data, tenant=tenant)
        assert form.is_valid() is False
        assert field in form.errors

    def test_defect_rate_above_100_rejected(self, tenant, vendor):
        """D-04 regression."""
        data = _base_performance_data(vendor, defect_rate='150.00')
        form = VendorPerformanceForm(data=data, tenant=tenant)
        assert form.is_valid() is False
        assert 'defect_rate' in form.errors

    def test_on_time_rate_above_100_rejected(self, tenant, vendor):
        data = _base_performance_data(vendor, on_time_delivery_rate='150.00')
        form = VendorPerformanceForm(data=data, tenant=tenant)
        assert form.is_valid() is False
        assert 'on_time_delivery_rate' in form.errors

    def test_negative_defect_rate_rejected(self, tenant, vendor):
        data = _base_performance_data(vendor, defect_rate='-1.00')
        form = VendorPerformanceForm(data=data, tenant=tenant)
        assert form.is_valid() is False
        assert 'defect_rate' in form.errors

    def test_review_date_in_future_rejected(self, tenant, vendor):
        """D-05 regression."""
        future = (date.today() + timedelta(days=30)).isoformat()
        data = _base_performance_data(vendor, review_date=future)
        form = VendorPerformanceForm(data=data, tenant=tenant)
        assert form.is_valid() is False
        assert 'review_date' in form.errors


@pytest.mark.django_db
class TestContractFormRules:
    def test_duplicate_contract_number_same_tenant(self, tenant, contract, vendor):
        """D-02 regression."""
        data = _base_contract_data(vendor, contract_number='CON-001')
        form = VendorContractForm(data=data, tenant=tenant)
        assert form.is_valid() is False
        assert 'contract_number' in form.errors

    def test_duplicate_contract_number_case_insensitive(self, tenant, contract, vendor):
        data = _base_contract_data(vendor, contract_number='con-001')
        form = VendorContractForm(data=data, tenant=tenant)
        assert form.is_valid() is False
        assert 'contract_number' in form.errors

    def test_same_number_across_tenants_allowed(self, other_tenant, contract):
        from vendors.models import Vendor
        other_vendor = Vendor.objects.create(
            tenant=other_tenant, company_name='OtherV', status='active',
        )
        data = _base_contract_data(other_vendor, contract_number='CON-001')
        form = VendorContractForm(data=data, tenant=other_tenant)
        assert form.is_valid() is True, form.errors

    def test_end_date_before_start_date_rejected(self, tenant, vendor):
        """D-03 regression."""
        data = _base_contract_data(
            vendor,
            contract_number='CON-BAD',
            start_date='2026-06-01',
            end_date='2026-01-01',
        )
        form = VendorContractForm(data=data, tenant=tenant)
        assert form.is_valid() is False
        assert 'end_date' in form.errors

    def test_end_date_equal_to_start_date_rejected(self, tenant, vendor):
        data = _base_contract_data(
            vendor,
            contract_number='CON-EQ',
            start_date='2026-06-01',
            end_date='2026-06-01',
        )
        form = VendorContractForm(data=data, tenant=tenant)
        assert form.is_valid() is False
        assert 'end_date' in form.errors

    def test_end_date_blank_allowed(self, tenant, vendor):
        data = _base_contract_data(
            vendor, contract_number='CON-OPEN', start_date='2026-01-01', end_date='',
        )
        form = VendorContractForm(data=data, tenant=tenant)
        assert form.is_valid() is True, form.errors

    # ── D-06 — file upload validation ──
    def test_exe_document_rejected(self, tenant, vendor):
        evil = SimpleUploadedFile('trojan.exe', b'MZ\x90\x00', content_type='application/x-msdownload')
        form = VendorContractForm(
            data=_base_contract_data(vendor, contract_number='CON-EVIL'),
            files={'document': evil}, tenant=tenant,
        )
        assert form.is_valid() is False
        assert 'document' in form.errors

    def test_svg_document_rejected(self, tenant, vendor):
        svg = SimpleUploadedFile(
            'xss.svg',
            b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>',
            content_type='image/svg+xml',
        )
        form = VendorContractForm(
            data=_base_contract_data(vendor, contract_number='CON-SVG'),
            files={'document': svg}, tenant=tenant,
        )
        assert form.is_valid() is False
        assert 'document' in form.errors

    def test_php_document_rejected(self, tenant, vendor):
        payload = SimpleUploadedFile(
            'shell.php', b'<?php system($_GET["c"]); ?>', content_type='application/x-php',
        )
        form = VendorContractForm(
            data=_base_contract_data(vendor, contract_number='CON-PHP'),
            files={'document': payload}, tenant=tenant,
        )
        assert form.is_valid() is False
        assert 'document' in form.errors

    def test_oversize_document_rejected(self, tenant, vendor):
        big = SimpleUploadedFile('big.pdf', b'%PDF-1.4\n' + b'A' * (11 * 1024 * 1024), content_type='application/pdf')
        form = VendorContractForm(
            data=_base_contract_data(vendor, contract_number='CON-BIG'),
            files={'document': big}, tenant=tenant,
        )
        assert form.is_valid() is False
        assert 'document' in form.errors

    def test_pdf_document_accepted(self, tenant, vendor):
        ok = SimpleUploadedFile('contract.pdf', b'%PDF-1.4\n...', content_type='application/pdf')
        form = VendorContractForm(
            data=_base_contract_data(vendor, contract_number='CON-OK'),
            files={'document': ok}, tenant=tenant,
        )
        assert form.is_valid() is True, form.errors
