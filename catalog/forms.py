from django import forms
from django.forms import inlineformset_factory
from django.core.validators import FileExtensionValidator
from django.core.exceptions import ValidationError
from .models import Category, Product, ProductAttribute, ProductImage, ProductDocument

ALLOWED_IMAGE_EXTENSIONS = ['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp']
ALLOWED_DOCUMENT_EXTENSIONS = ['pdf', 'doc', 'docx', 'xls', 'xlsx', 'csv', 'txt', 'rtf', 'odt']
MAX_IMAGE_SIZE_MB = 5
MAX_DOCUMENT_SIZE_MB = 20


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ['name', 'parent', 'description', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter category name',
            }),
            'parent': forms.Select(attrs={
                'class': 'form-select',
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Enter description (optional)',
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
                'role': 'switch',
            }),
        }

    def _get_descendant_ids(self, category):
        """Recursively collect all descendant IDs to prevent circular hierarchy."""
        ids = []
        for child in Category.objects.filter(parent=category):
            ids.append(child.pk)
            ids.extend(self._get_descendant_ids(child))
        return ids

    def __init__(self, *args, tenant=None, **kwargs):
        self.tenant = tenant
        super().__init__(*args, **kwargs)
        if tenant:
            # Filter parent choices to same tenant, exclude self to prevent circular refs
            parent_qs = Category.objects.filter(tenant=tenant, is_active=True)
            if self.instance and self.instance.pk:
                # Exclude self and ALL descendants to prevent circular hierarchy
                exclude_ids = [self.instance.pk] + self._get_descendant_ids(self.instance)
                parent_qs = parent_qs.exclude(pk__in=exclude_ids)
            # Only allow departments and categories as parents (max 3 levels)
            parent_qs = parent_qs.filter(level__in=['department', 'category'])
            self.fields['parent'].queryset = parent_qs
            self.fields['parent'].required = False
            self.fields['parent'].empty_label = '— No Parent (Department) —'

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.tenant:
            instance.tenant = self.tenant
        if commit:
            instance.save()
        return instance


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = [
            'sku', 'name', 'description', 'category', 'status',
            'purchase_cost', 'wholesale_price', 'retail_price', 'markup_percentage',
            'weight', 'length', 'width', 'height',
            'barcode', 'brand', 'manufacturer', 'is_active',
        ]
        widgets = {
            'sku': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., ELEC-LAP-001',
            }),
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter product name',
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Enter product description (optional)',
            }),
            'category': forms.Select(attrs={
                'class': 'form-select',
            }),
            'status': forms.Select(attrs={
                'class': 'form-select',
            }),
            'purchase_cost': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0',
            }),
            'wholesale_price': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0',
            }),
            'retail_price': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0',
            }),
            'markup_percentage': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0',
            }),
            'weight': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.001',
                'min': '0',
                'placeholder': 'kg',
            }),
            'length': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0',
                'placeholder': 'cm',
            }),
            'width': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0',
                'placeholder': 'cm',
            }),
            'height': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0',
                'placeholder': 'cm',
            }),
            'barcode': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter barcode (optional)',
            }),
            'brand': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter brand (optional)',
            }),
            'manufacturer': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter manufacturer (optional)',
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
                'role': 'switch',
            }),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        self.tenant = tenant
        super().__init__(*args, **kwargs)
        if tenant:
            self.fields['category'].queryset = Category.objects.filter(
                tenant=tenant, is_active=True
            )
            self.fields['category'].required = False
            self.fields['category'].empty_label = '— Select Category —'

    def clean(self):
        cleaned_data = super().clean()
        purchase_cost = cleaned_data.get('purchase_cost')
        retail_price = cleaned_data.get('retail_price')
        wholesale_price = cleaned_data.get('wholesale_price')
        markup = cleaned_data.get('markup_percentage')

        # Auto-calculate markup if purchase cost and retail price are provided
        if purchase_cost and retail_price and purchase_cost > 0:
            expected_markup = ((retail_price - purchase_cost) / purchase_cost) * 100
            # If markup was left at default (0) or blank, auto-fill it
            if not markup:
                cleaned_data['markup_percentage'] = round(expected_markup, 2)

        # Warn if wholesale is higher than retail
        if wholesale_price and retail_price and wholesale_price > retail_price:
            self.add_error('wholesale_price', 'Wholesale price should not exceed retail price.')

        # Warn if purchase cost is higher than retail
        if purchase_cost and retail_price and purchase_cost > retail_price:
            self.add_error('purchase_cost', 'Purchase cost exceeds retail price — negative margin.')

        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.tenant:
            instance.tenant = self.tenant
        if commit:
            instance.save()
        return instance


class ProductAttributeForm(forms.ModelForm):
    class Meta:
        model = ProductAttribute
        fields = ['name', 'value', 'attr_type', 'sort_order']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control form-control-sm',
                'placeholder': 'e.g., Color',
            }),
            'value': forms.TextInput(attrs={
                'class': 'form-control form-control-sm',
                'placeholder': 'e.g., Black',
            }),
            'attr_type': forms.Select(attrs={
                'class': 'form-select form-select-sm',
            }),
            'sort_order': forms.NumberInput(attrs={
                'class': 'form-control form-control-sm',
                'min': '0',
                'style': 'width: 70px;',
            }),
        }


ProductAttributeFormSet = inlineformset_factory(
    Product,
    ProductAttribute,
    form=ProductAttributeForm,
    extra=3,
    can_delete=True,
)


class ProductImageForm(forms.ModelForm):
    class Meta:
        model = ProductImage
        fields = ['image', 'caption', 'is_primary']
        widgets = {
            'image': forms.ClearableFileInput(attrs={
                'class': 'form-control',
                'accept': 'image/*',
            }),
            'caption': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Image caption (optional)',
            }),
            'is_primary': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['image'].validators.append(
            FileExtensionValidator(allowed_extensions=ALLOWED_IMAGE_EXTENSIONS)
        )

    def clean_image(self):
        image = self.cleaned_data.get('image')
        if image and image.size > MAX_IMAGE_SIZE_MB * 1024 * 1024:
            raise ValidationError(f'Image file size must be under {MAX_IMAGE_SIZE_MB} MB.')
        return image


class ProductDocumentForm(forms.ModelForm):
    class Meta:
        model = ProductDocument
        fields = ['title', 'file', 'doc_type']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Document title',
            }),
            'file': forms.ClearableFileInput(attrs={
                'class': 'form-control',
            }),
            'doc_type': forms.Select(attrs={
                'class': 'form-select',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['file'].validators.append(
            FileExtensionValidator(allowed_extensions=ALLOWED_DOCUMENT_EXTENSIONS)
        )

    def clean_file(self):
        file = self.cleaned_data.get('file')
        if file and file.size > MAX_DOCUMENT_SIZE_MB * 1024 * 1024:
            raise ValidationError(f'Document file size must be under {MAX_DOCUMENT_SIZE_MB} MB.')
        return file
