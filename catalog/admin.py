from django.contrib import admin
from .models import Category, Product, ProductAttribute, ProductImage, ProductDocument


class ProductAttributeInline(admin.TabularInline):
    model = ProductAttribute
    extra = 1


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1


class ProductDocumentInline(admin.TabularInline):
    model = ProductDocument
    extra = 1


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'tenant', 'parent', 'level', 'is_active', 'created_at')
    list_filter = ('level', 'is_active', 'tenant')
    search_fields = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)}


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('sku', 'name', 'tenant', 'category', 'status', 'tax_category', 'retail_price', 'created_at')
    list_filter = ('status', 'is_active', 'tax_category', 'tenant')
    search_fields = ('sku', 'name', 'barcode', 'hsn_code')
    inlines = [ProductAttributeInline, ProductImageInline, ProductDocumentInline]


@admin.register(ProductAttribute)
class ProductAttributeAdmin(admin.ModelAdmin):
    list_display = ('name', 'value', 'attr_type', 'product', 'tenant')
    list_filter = ('attr_type', 'tenant')
    search_fields = ('name', 'value')


@admin.register(ProductImage)
class ProductImageAdmin(admin.ModelAdmin):
    list_display = ('product', 'caption', 'is_primary', 'uploaded_at')
    list_filter = ('is_primary', 'tenant')


@admin.register(ProductDocument)
class ProductDocumentAdmin(admin.ModelAdmin):
    list_display = ('title', 'product', 'doc_type', 'uploaded_at')
    list_filter = ('doc_type', 'tenant')
    search_fields = ('title',)
