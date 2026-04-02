import uuid
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.text import slugify

from core.models import Role, Tenant, User, UserInvite, UserRole

from .forms import (
    AcceptInviteForm,
    ChangePasswordForm,
    ForgotPasswordForm,
    LoginForm,
    ProfileUpdateForm,
    RegisterForm,
    UserInviteForm,
)


def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    form = LoginForm()

    if request.method == 'POST':
        form = LoginForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data['username']
            password = form.cleaned_data['password']
            remember = form.cleaned_data.get('remember', False)

            user = authenticate(request, username=username, password=password)
            if user is not None:
                login(request, user)
                if not remember:
                    request.session.set_expiry(0)
                messages.success(request, f'Welcome back, {user.get_full_name() or user.username}!')
                return redirect('dashboard')
            else:
                messages.error(request, 'Invalid username or password.')

    return render(request, 'auth/login.html', {'form': form})


def register_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    form = RegisterForm()

    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            company_name = form.cleaned_data['company_name']
            slug = slugify(company_name)

            # Ensure slug uniqueness
            base_slug = slug
            counter = 1
            while Tenant.objects.filter(slug=slug).exists():
                slug = f'{base_slug}-{counter}'
                counter += 1

            tenant = Tenant.objects.create(
                name=company_name,
                slug=slug,
            )

            user = User.objects.create_user(
                username=form.cleaned_data['username'],
                email=form.cleaned_data['email'],
                password=form.cleaned_data['password'],
                first_name=form.cleaned_data['first_name'],
                last_name=form.cleaned_data['last_name'],
                tenant=tenant,
                is_tenant_admin=True,
            )

            login(request, user)
            messages.success(request, 'Account created successfully! Welcome to NavIMS.')
            return redirect('dashboard')

    return render(request, 'auth/register.html', {'form': form})


def logout_view(request):
    if request.method == 'POST':
        logout(request)
        messages.success(request, 'You have been logged out.')
    return redirect('accounts:login')


def forgot_password_view(request):
    form = ForgotPasswordForm()

    if request.method == 'POST':
        form = ForgotPasswordForm(request.POST)
        if form.is_valid():
            messages.success(
                request,
                'If an account with that email exists, a password reset link has been sent.',
            )
            return redirect('accounts:login')

    return render(request, 'auth/forgot_password.html', {'form': form})


@login_required
def profile_view(request):
    form = ProfileUpdateForm(instance=request.user)

    if request.method == 'POST':
        form = ProfileUpdateForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Profile updated successfully.')
            return redirect('accounts:profile')

    return render(request, 'accounts/profile.html', {'form': form})


@login_required
def change_password_view(request):
    if request.method == 'POST':
        form = ChangePasswordForm(request.user, request.POST)
        if form.is_valid():
            request.user.set_password(form.cleaned_data['new_password'])
            request.user.save()
            update_session_auth_hash(request, request.user)
            messages.success(request, 'Password changed successfully.')
        else:
            for error in form.errors.values():
                messages.error(request, error)

    return redirect('accounts:profile')


@login_required
def user_list_view(request):
    users = User.objects.filter(tenant=request.tenant)

    # Search filter
    query = request.GET.get('q', '').strip()
    if query:
        users = users.filter(
            Q(username__icontains=query)
            | Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
            | Q(email__icontains=query)
        )

    # Status filter
    status = request.GET.get('status', '').strip()
    if status == 'active':
        users = users.filter(is_active=True)
    elif status == 'inactive':
        users = users.filter(is_active=False)

    paginator = Paginator(users, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    roles = Role.objects.filter(tenant=request.tenant)

    return render(request, 'accounts/user_list.html', {
        'users': page_obj,
        'roles': roles,
        'query': query,
        'status': status,
    })


@login_required
def user_invite_view(request):
    form = UserInviteForm(tenant=request.tenant)

    if request.method == 'POST':
        form = UserInviteForm(request.tenant, request.POST)
        if form.is_valid():
            invite = UserInvite.objects.create(
                tenant=request.tenant,
                email=form.cleaned_data['email'],
                role=form.cleaned_data['role'],
                invited_by=request.user,
                expires_at=timezone.now() + timedelta(days=7),
            )
            messages.success(
                request,
                f'Invitation sent to {invite.email}. The invite link is valid for 7 days.',
            )
            return redirect('accounts:user_list')

    return render(request, 'accounts/user_invite.html', {'form': form})


def accept_invite_view(request, token):
    invite = get_object_or_404(UserInvite, token=token, status='pending')

    if invite.expires_at < timezone.now():
        invite.status = 'expired'
        invite.save()
        messages.error(request, 'This invitation has expired.')
        return redirect('accounts:login')

    form = AcceptInviteForm()

    if request.method == 'POST':
        form = AcceptInviteForm(request.POST)
        if form.is_valid():
            # Create user from invite
            username = invite.email.split('@')[0]
            base_username = username
            counter = 1
            while User.objects.filter(username=username).exists():
                username = f'{base_username}{counter}'
                counter += 1

            user = User.objects.create_user(
                username=username,
                email=invite.email,
                password=form.cleaned_data['password'],
                tenant=invite.tenant,
            )

            # Assign role if specified
            if invite.role:
                UserRole.objects.create(user=user, role=invite.role)

            invite.status = 'accepted'
            invite.save()

            login(request, user)
            messages.success(request, 'Account created successfully! Welcome to NavIMS.')
            return redirect('dashboard')

    return render(request, 'auth/accept_invite.html', {
        'form': form,
        'invite': invite,
    })


@login_required
def user_edit_view(request, pk):
    user = get_object_or_404(User, pk=pk, tenant=request.tenant)

    if request.method == 'POST':
        user.first_name = request.POST.get('first_name', user.first_name)
        user.last_name = request.POST.get('last_name', user.last_name)
        user.email = request.POST.get('email', user.email)
        user.is_active = request.POST.get('is_active') == 'on'

        role_id = request.POST.get('role')
        if role_id:
            role = get_object_or_404(Role, pk=role_id, tenant=request.tenant)
            UserRole.objects.filter(user=user).delete()
            UserRole.objects.create(user=user, role=role)

        user.save()
        messages.success(request, f'User {user.get_full_name() or user.username} updated successfully.')
        return redirect('accounts:user_list')

    roles = Role.objects.filter(tenant=request.tenant)
    current_role = UserRole.objects.filter(user=user).first()

    return render(request, 'accounts/user_edit.html', {
        'edit_user': user,
        'roles': roles,
        'current_role': current_role,
    })


@login_required
def user_delete_view(request, pk):
    if request.method == 'POST':
        user = get_object_or_404(User, pk=pk, tenant=request.tenant)
        username = user.get_full_name() or user.username
        user.delete()
        messages.success(request, f'User {username} has been deleted.')

    return redirect('accounts:user_list')
