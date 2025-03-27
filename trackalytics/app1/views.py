from django.shortcuts import render, redirect
from django.http import HttpResponse, JsonResponse, StreamingHttpResponse
from django.contrib import messages
from django.contrib.auth import authenticate, login
from django.contrib.auth.views import LoginView
from django.urls import reverse_lazy
from .models import Product, Inventory, InventoryHistory, ReportExport, ActivityLog, InventoryNotification
from .forms import AddInventoryForm, RemoveInventoryForm, ExportForm, ProductForm, RegistrationForm
from django.utils import timezone
import csv
import json
import time
from django.template.loader import get_template
from xhtml2pdf import pisa
from django.db.models import Sum, F

# Dashboard View (No login required)
def dashboard(request):
    total_inventory = Inventory.objects.count()
    low_stock_items = Inventory.objects.filter(quantity__lte=10).count()
    zero_stock_items = Inventory.objects.filter(quantity=0).count()
    
    # Get low stock products for SSE demo
    low_stock_products = Product.objects.annotate(
        total_quantity=Sum('inventory__quantity')
    ).filter(total_quantity__lt=F('low_stock_threshold'))
    
    # Log action only if user is authenticated
    if request.user.is_authenticated:
        ActivityLog.objects.create(user=request.user, action='Viewed dashboard')
    
    context = {
        'total_inventory': total_inventory,
        'low_stock_items': low_stock_items,
        'zero_stock_items': zero_stock_items,
        'low_stock_products': low_stock_products,
    }
    return render(request, 'dashboard.html', context)

# Inventory Stream View for SSE
def inventory_stream(request):
    def event_stream():
        last_checked = time.time()
        while True:
            # Check for new low stock items every 5 seconds
            if time.time() - last_checked > 5:
                last_checked = time.time()
                
                # Get low stock products
                low_stock_products = Product.objects.annotate(
                    total_quantity=Sum('inventory__quantity')
                ).filter(
                    total_quantity__lt=F('low_stock_threshold')
                ).values('id', 'product_name', 'total_quantity', 'low_stock_threshold')
                
                # Get unread notifications for authenticated users
                notifications = []
                if request.user.is_authenticated:
                    notifications = InventoryNotification.objects.filter(
                        is_read=False,
                        recipients=request.user
                    ).order_by('-created_at')[:5].values('id', 'message')
                
                yield f"data: {json.dumps({
                    'low_stock': list(low_stock_products),
                    'notifications': list(notifications),
                    'timestamp': time.time()
                })}\n\n"
            
            time.sleep(1)
    
    response = StreamingHttpResponse(event_stream(), content_type='text/event-stream')
    response['Cache-Control'] = 'no-cache'
    return response

# Mark notification as read
def mark_notification_read(request, notification_id):
    if request.user.is_authenticated:
        try:
            notification = InventoryNotification.objects.get(
                id=notification_id,
                recipients=request.user
            )
            notification.is_read = True
            notification.save()
            return JsonResponse({'success': True})
        except InventoryNotification.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Notification not found'}, status=404)
    return JsonResponse({'success': False, 'error': 'Authentication required'}, status=403)

# Inventory View (No login required)
def inventory(request):
    add_form = AddInventoryForm(request.POST or None)
    remove_form = RemoveInventoryForm(request.POST or None)
    products = Product.objects.all()
    
    if request.method == 'POST':
        if 'add_inventory' in request.POST and add_form.is_valid():
            instance = add_form.save()
            InventoryHistory.objects.create(inventory=instance, action='received', quantity=instance.quantity)
            
            # Check for low stock after adding inventory
            product = instance.product
            if product.is_low_stock():
                notification = InventoryNotification.objects.create(
                    product=product,
                    notification_type='low_stock',
                    message=f'Low stock alert for {product.product_name}. Current quantity: {product.total_quantity}'
                )
                # Add appropriate recipients (e.g., managers)
                managers = request.user.groups.filter(name='Inventory Managers').first()
                if managers:
                    notification.recipients.set(managers.user_set.all())
            
            if request.user.is_authenticated:
                ActivityLog.objects.create(user=request.user, action='Added inventory')
            messages.success(request, 'Inventory item added successfully!')
            return redirect('app1:inventory')
        
        if 'remove_inventory' in request.POST and remove_form.is_valid():
            product = remove_form.cleaned_data['product']
            quantity = remove_form.cleaned_data['quantity']
            inventory_item = Inventory.objects.filter(product=product).first()
            
            if inventory_item:
                inventory_item.quantity -= quantity
                inventory_item.save()
                InventoryHistory.objects.create(inventory=inventory_item, action='sold', quantity=quantity)
                
                # Check for low stock after removing inventory
                if product.is_low_stock():
                    notification = InventoryNotification.objects.create(
                        product=product,
                        notification_type='low_stock',
                        message=f'Low stock alert for {product.product_name}. Current quantity: {product.total_quantity}'
                    )
                    # Add appropriate recipients
                    managers = request.user.groups.filter(name='Inventory Managers').first()
                    if managers:
                        notification.recipients.set(managers.user_set.all())
                
                if request.user.is_authenticated:
                    ActivityLog.objects.create(user=request.user, action='Removed inventory')
                
                return JsonResponse({
                    'success': True,
                    'inventory': list(Inventory.objects.values('product__product_name', 'quantity')),
                    'low_stock': product.is_low_stock()
                })
            else:
                return JsonResponse({'success': False, 'error': 'Inventory item not found'})
    
    if request.method == 'GET' and request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        inventory_data = list(Inventory.objects.values('product__product_name', 'quantity'))
        low_stock = list(Product.objects.annotate(
            total_quantity=Sum('inventory__quantity')
        ).filter(
            total_quantity__lt=F('low_stock_threshold')
        ).values('id', 'product_name', 'total_quantity', 'low_stock_threshold'))
        
        return JsonResponse({
            'inventory': inventory_data,
            'low_stock': low_stock
        })
    
    products_json = json.dumps([{'id': p.id, 'product_name': p.product_name} for p in products])
    context = {
        'add_form': add_form,
        'remove_form': remove_form,
        'inventory': Inventory.objects.all(),
        'products_json': products_json,
    }
    return render(request, 'inventory.html', context)

# Product List View (No login required)
def product_list(request):
    products = Product.objects.all()
    return render(request, 'products.html', {'products': products})

# Product Create View (No login required)
def product_create(request):
    if request.method == 'POST':
        form = ProductForm(request.POST)
        if form.is_valid():
            form.save()
            if request.user.is_authenticated:
                ActivityLog.objects.create(user=request.user, action='Created product')
            messages.success(request, 'Product added successfully!')
            return redirect('app1:product_list')
    else:
        form = ProductForm()
    return render(request, 'product_form.html', {'form': form})

# Inventory History View (No login required)
def inventory_history(request):
    history = InventoryHistory.objects.all().order_by('-transaction_date')
    return render(request, 'inventory_history.html', {'history': history})

# Reports & Exports View (No login required)
def reports_exports(request):
    if request.method == 'POST':
        form = ExportForm(request.POST)
        if form.is_valid():
            report = form.save(commit=False)
            if request.user.is_authenticated:
                report.user = request.user
                ActivityLog.objects.create(user=request.user, action='Requested report export')
            report.save()
            messages.success(request, 'Export request saved successfully!')
            return redirect('app1:reports_exports')
    else:
        form = ExportForm()
    
    context = {
        'form': form,
        # Show all reports if unauthenticated, filter by user if authenticated
        'reports': ReportExport.objects.filter(user=request.user) if request.user.is_authenticated else ReportExport.objects.all(),
    }
    return render(request, 'reports_exports.html', context)

# Generate Inventory Report (No login required)
def generate_inventory_report(request):
    if request.method == 'POST':
        start_date = request.POST.get('start_date')
        end_date = request.POST.get('end_date')
        inventory_items = Inventory.objects.all()
        if start_date and end_date:
            inventory_items = inventory_items.filter(last_updated__range=[start_date, end_date])
        
        if request.user.is_authenticated:
            ActivityLog.objects.create(user=request.user, action='Generated inventory report')
        return JsonResponse({
            'success': True,
            'message': 'Report generated successfully!',
            'data': list(inventory_items.values('product__product_name', 'quantity', 'location'))
        })
    return JsonResponse({'error': 'Invalid request'}, status=400)

# Export Data (No login required)
def export_data(request):
    if request.method == 'POST':
        export_format = request.POST.get('export_format')
        
        if export_format == 'CSV':
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = 'attachment; filename="inventory_export.csv"'
            writer = csv.writer(response)
            writer.writerow(['Product', 'Batch Number', 'Serial Number', 'Quantity', 'Location'])
            for item in Inventory.objects.all():
                writer.writerow([item.product.product_name, item.batch_number, item.serial_number, item.quantity, item.location])
            if request.user.is_authenticated:
                ActivityLog.objects.create(user=request.user, action='Exported inventory as CSV')
            return response
        
        elif export_format == 'PDF':
            template = get_template('reports/inventory_pdf.html')
            context = {'inventory': Inventory.objects.all()}
            html = template.render(context)
            response = HttpResponse(content_type='application/pdf')
            response['Content-Disposition'] = 'attachment; filename="inventory_export.pdf"'
            pisa_status = pisa.CreatePDF(html, dest=response)
            if pisa_status.err:
                return HttpResponse('Error generating PDF', status=500)
            if request.user.is_authenticated:
                ActivityLog.objects.create(user=request.user, action='Exported inventory as PDF')
            return response
        
        elif export_format == 'Excel':
            if request.user.is_authenticated:
                ActivityLog.objects.create(user=request.user, action='Attempted Excel export (not implemented)')
            return HttpResponse('Excel export not implemented yet', status=501)
    
    return JsonResponse({'error': 'Invalid request'}, status=400)

# Activity Log View (No login required)
def activity_log(request):
    # Show user-specific logs if authenticated, all logs if not
    logs = ActivityLog.objects.filter(user=request.user) if request.user.is_authenticated else ActivityLog.objects.all()
    logs = logs.order_by('-timestamp')
    return render(request, 'activity_log.html', {'logs': logs})

# Registration View (No login required)
def register(request):
    if request.method == 'POST':
        form = RegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            ActivityLog.objects.create(user=user, action='Registered new user')
            messages.success(request, 'Registration successful! Welcome!')
            return redirect('app1:dashboard')
    else:
        form = RegistrationForm()
    return render(request, 'registration/register.html', {'form': form})

# Custom Login View
class CustomLoginView(LoginView):
    template_name = 'registration/login.html'
    
    def post(self, request, *args, **kwargs):
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '').strip()
        
        # If no username or password provided, skip authentication and proceed
        if not username and not password:
            # Log as guest if not authenticated, or as current user if already logged in
            if request.user.is_authenticated:
                ActivityLog.objects.create(user=request.user, action='Skipped login as authenticated user')
            else:
                ActivityLog.objects.create(user=None, action='Skipped login as guest')
            return redirect(self.get_success_url())
        
        # Otherwise, proceed with normal authentication
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            ActivityLog.objects.create(user=user, action='Logged in')
            return redirect(self.get_success_url())
        else:
            # Handle invalid login
            return self.form_invalid(self.get_form())

    def get_success_url(self):
        return reverse_lazy('app1:dashboard')