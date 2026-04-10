from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, Count

from .models import Category, Product, ProductImage, ProductDocument
from .forms import (
    CategoryForm,
    ProductForm,
    ProductAttributeFormSet,
    ProductImageForm,
    ProductDocumentForm,
)


# ──────────────────────────────────────────────
# Category views
# ──────────────────────────────────────────────

@login_required
def category_list_view(request):
    tenant = request.tenant
    queryset = Category.objects.filter(tenant=tenant).select_related(
        'parent__parent',
    ).annotate(
        # Count products in this category + child categories + grandchild categories
        product_count=Count(
            'products', distinct=True,
        ) + Count(
            'children__products', distinct=True,
        ) + Count(
            'children__children__products', distinct=True,
        ),
    )

    # Search
    q = request.GET.get('q', '').strip()
    if q:
        queryset = queryset.filter(name__icontains=q)

    # Filter by level
    level = request.GET.get('level', '')
    if level:
        queryset = queryset.filter(level=level)

    # Filter by status
    status = request.GET.get('status', '')
    if status == 'active':
        queryset = queryset.filter(is_active=True)
    elif status == 'inactive':
        queryset = queryset.filter(is_active=False)

    paginator = Paginator(queryset, 20)
    page_number = request.GET.get('page')
    categories = paginator.get_page(page_number)

    context = {
        'categories': categories,
        'q': q,
        'level_choices': Category.LEVEL_CHOICES,
        'current_level': level,
        'current_status': status,
    }
    return render(request, 'catalog/category_list.html', context)


@login_required
def category_create_view(request):
    tenant = request.tenant

    if request.method == 'POST':
        form = CategoryForm(request.POST, tenant=tenant)
        if form.is_valid():
            category = form.save()
            messages.success(request, f'Category "{category.name}" created successfully.')
            return redirect('catalog:category_list')
    else:
        form = CategoryForm(tenant=tenant)

    context = {
        'form': form,
        'title': 'Add Category',
    }
    return render(request, 'catalog/category_form.html', context)


@login_required
def category_detail_view(request, pk):
    tenant = request.tenant
    category = get_object_or_404(Category, pk=pk, tenant=tenant)
    children = Category.objects.filter(tenant=tenant, parent=category)
    products = Product.objects.filter(tenant=tenant, category=category)

    context = {
        'category': category,
        'children': children,
        'products': products,
    }
    return render(request, 'catalog/category_detail.html', context)


@login_required
def category_edit_view(request, pk):
    tenant = request.tenant
    category = get_object_or_404(Category, pk=pk, tenant=tenant)

    if request.method == 'POST':
        form = CategoryForm(request.POST, instance=category, tenant=tenant)
        if form.is_valid():
            form.save()
            messages.success(request, f'Category "{category.name}" updated successfully.')
            return redirect('catalog:category_detail', pk=category.pk)
    else:
        form = CategoryForm(instance=category, tenant=tenant)

    context = {
        'form': form,
        'title': 'Edit Category',
        'category': category,
    }
    return render(request, 'catalog/category_form.html', context)


@login_required
def category_delete_view(request, pk):
    tenant = request.tenant

    if request.method != 'POST':
        return redirect('catalog:category_list')

    category = get_object_or_404(Category, pk=pk, tenant=tenant)

    # Prevent deletion if category has children
    child_count = Category.objects.filter(tenant=tenant, parent=category).count()
    if child_count > 0:
        messages.error(
            request,
            f'Cannot delete "{category.name}" — it has {child_count} child '
            f'categor{"ies" if child_count != 1 else "y"}. Delete or reassign them first.',
        )
        return redirect('catalog:category_detail', pk=category.pk)

    # Prevent deletion if category has products
    product_count = Product.objects.filter(tenant=tenant, category=category).count()
    if product_count > 0:
        messages.error(
            request,
            f'Cannot delete "{category.name}" — it has {product_count} '
            f'product{"s" if product_count != 1 else ""}. Reassign them first.',
        )
        return redirect('catalog:category_detail', pk=category.pk)

    category_name = category.name
    category.delete()
    messages.success(request, f'Category "{category_name}" deleted successfully.')
    return redirect('catalog:category_list')


# ──────────────────────────────────────────────
# Product views
# ──────────────────────────────────────────────

@login_required
def product_list_view(request):
    tenant = request.tenant
    queryset = Product.objects.filter(tenant=tenant).select_related('category')

    # Search
    q = request.GET.get('q', '').strip()
    if q:
        queryset = queryset.filter(
            Q(name__icontains=q) | Q(sku__icontains=q) | Q(barcode__icontains=q)
        )

    # Filter by status (validate against known choices)
    status = request.GET.get('status', '')
    valid_statuses = [choice[0] for choice in Product.STATUS_CHOICES]
    if status and status in valid_statuses:
        queryset = queryset.filter(status=status)

    # Filter by category
    category_id = request.GET.get('category', '')
    if category_id:
        queryset = queryset.filter(category_id=category_id)

    paginator = Paginator(queryset, 20)
    page_number = request.GET.get('page')
    products = paginator.get_page(page_number)

    context = {
        'products': products,
        'q': q,
        'status_choices': Product.STATUS_CHOICES,
        'categories': Category.objects.filter(tenant=tenant, is_active=True).select_related('parent__parent'),
        'current_status': status,
        'current_category': category_id,
    }
    return render(request, 'catalog/product_list.html', context)


@login_required
def product_create_view(request):
    tenant = request.tenant

    if request.method == 'POST':
        form = ProductForm(request.POST, tenant=tenant)
        formset = ProductAttributeFormSet(request.POST, prefix='attributes')
        if form.is_valid() and formset.is_valid():
            product = form.save()
            formset.instance = product
            attributes = formset.save(commit=False)
            for attr in attributes:
                attr.tenant = tenant
                attr.save()
            for obj in formset.deleted_objects:
                obj.delete()
            messages.success(request, f'Product "{product.name}" created successfully.')
            return redirect('catalog:product_detail', pk=product.pk)
    else:
        form = ProductForm(tenant=tenant)
        formset = ProductAttributeFormSet(prefix='attributes')

    context = {
        'form': form,
        'formset': formset,
        'title': 'Add Product',
    }
    return render(request, 'catalog/product_form.html', context)


@login_required
def product_detail_view(request, pk):
    tenant = request.tenant
    product = get_object_or_404(
        Product.objects.select_related('category'),
        pk=pk, tenant=tenant,
    )
    attributes = product.attributes.all()
    images = product.images.all()
    documents = product.documents.all()

    image_form = ProductImageForm()
    document_form = ProductDocumentForm()

    context = {
        'product': product,
        'attributes': attributes,
        'images': images,
        'documents': documents,
        'image_form': image_form,
        'document_form': document_form,
    }
    return render(request, 'catalog/product_detail.html', context)


@login_required
def product_edit_view(request, pk):
    tenant = request.tenant
    product = get_object_or_404(Product, pk=pk, tenant=tenant)

    if request.method == 'POST':
        form = ProductForm(request.POST, instance=product, tenant=tenant)
        formset = ProductAttributeFormSet(
            request.POST, instance=product, prefix='attributes',
        )
        if form.is_valid() and formset.is_valid():
            form.save()
            attributes = formset.save(commit=False)
            for attr in attributes:
                attr.tenant = tenant
                attr.save()
            for obj in formset.deleted_objects:
                obj.delete()
            messages.success(request, f'Product "{product.name}" updated successfully.')
            return redirect('catalog:product_detail', pk=product.pk)
    else:
        form = ProductForm(instance=product, tenant=tenant)
        formset = ProductAttributeFormSet(instance=product, prefix='attributes')

    context = {
        'form': form,
        'formset': formset,
        'title': 'Edit Product',
        'product': product,
    }
    return render(request, 'catalog/product_form.html', context)


@login_required
def product_delete_view(request, pk):
    tenant = request.tenant

    if request.method != 'POST':
        return redirect('catalog:product_list')

    product = get_object_or_404(Product, pk=pk, tenant=tenant)
    product_name = product.name
    product.delete()
    messages.success(request, f'Product "{product_name}" deleted successfully.')
    return redirect('catalog:product_list')


# ──────────────────────────────────────────────
# Product Image views (inline from detail page)
# ──────────────────────────────────────────────

@login_required
def product_image_upload_view(request, pk):
    tenant = request.tenant
    product = get_object_or_404(Product, pk=pk, tenant=tenant)

    if request.method == 'POST':
        form = ProductImageForm(request.POST, request.FILES)
        if form.is_valid():
            image = form.save(commit=False)
            image.tenant = tenant
            image.product = product
            image.save()
            messages.success(request, 'Image uploaded successfully.')
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f'Image upload error: {error}')

    return redirect('catalog:product_detail', pk=product.pk)


@login_required
def product_image_delete_view(request, pk, image_pk):
    tenant = request.tenant

    if request.method != 'POST':
        return redirect('catalog:product_detail', pk=pk)

    product = get_object_or_404(Product, pk=pk, tenant=tenant)
    image = get_object_or_404(ProductImage, pk=image_pk, product=product, tenant=tenant)
    image.delete()
    messages.success(request, 'Image deleted successfully.')
    return redirect('catalog:product_detail', pk=product.pk)


# ──────────────────────────────────────────────
# Product Document views (inline from detail page)
# ──────────────────────────────────────────────

@login_required
def product_document_upload_view(request, pk):
    tenant = request.tenant
    product = get_object_or_404(Product, pk=pk, tenant=tenant)

    if request.method == 'POST':
        form = ProductDocumentForm(request.POST, request.FILES)
        if form.is_valid():
            doc = form.save(commit=False)
            doc.tenant = tenant
            doc.product = product
            doc.save()
            messages.success(request, 'Document uploaded successfully.')
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f'Document upload error: {error}')

    return redirect('catalog:product_detail', pk=product.pk)


@login_required
def product_document_delete_view(request, pk, doc_pk):
    tenant = request.tenant

    if request.method != 'POST':
        return redirect('catalog:product_detail', pk=pk)

    product = get_object_or_404(Product, pk=pk, tenant=tenant)
    doc = get_object_or_404(ProductDocument, pk=doc_pk, product=product, tenant=tenant)
    doc.delete()
    messages.success(request, 'Document deleted successfully.')
    return redirect('catalog:product_detail', pk=product.pk)
