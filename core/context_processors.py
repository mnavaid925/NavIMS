def tenant_context(request):
    return {
        'current_tenant': getattr(request, 'tenant', None),
    }
