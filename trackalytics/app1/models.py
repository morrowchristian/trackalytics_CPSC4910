# app1/models.py

from django.db import models
from django.contrib.auth.models import User, Permission, Group  

# Products Table
class Product(models.Model):
    product_name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    category = models.CharField(max_length=100, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    low_stock_threshold = models.IntegerField(default=5)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.product_name

    @property
    def total_quantity(self):
        """Calculate total quantity across all inventory items for this product"""
        return self.inventory_set.aggregate(total=models.Sum('quantity'))['total'] or 0

    def is_low_stock(self):
        """Check if product is below low stock threshold"""
        return self.total_quantity < self.low_stock_threshold

# Inventory Table
class Inventory(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    batch_number = models.CharField(max_length=100, blank=True, null=True, db_index=True)
    serial_number = models.CharField(max_length=100, unique=True, db_index=True)
    quantity = models.IntegerField(default=0)
    location = models.CharField(max_length=255, blank=True, null=True)
    last_updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.product.product_name} - {self.serial_number}"

# Inventory History Table
class InventoryHistory(models.Model):
    ACTION_CHOICES = [
        ('received', 'Received'),
        ('sold', 'Sold'),
        ('damaged', 'Damaged'),
        ('adjustment', 'Adjustment'),
    ]
    inventory = models.ForeignKey(Inventory, on_delete=models.CASCADE)
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    quantity = models.IntegerField()
    transaction_date = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.inventory.product.product_name} - {self.action}"

# Roles Table
class Role(models.Model):
    role_name = models.CharField(max_length=50, unique=True)

    def __str__(self):
        return self.role_name

# Permissions Table
class Permission(models.Model):
    role = models.ForeignKey(Role, on_delete=models.CASCADE)
    permission_name = models.CharField(max_length=100)

    def __str__(self):
        return f"{self.role.role_name} - {self.permission_name}"

# Activity Logs Table
class ActivityLog(models.Model):
    user = models.ForeignKey('auth.User', on_delete=models.CASCADE, null=True, blank=True)  # Allow null
    action = models.CharField(max_length=255)
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username if self.user else 'Guest'} - {self.action} on {self.timestamp}"

# Report Exports Table
class ReportExport(models.Model):
    FILE_FORMAT_CHOICES = [
        ('CSV', 'CSV'),
        ('PDF', 'PDF'),
        ('Excel', 'Excel'),
    ]
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)  # Use Django's built-in User model
    file_format = models.CharField(max_length=10, choices=FILE_FORMAT_CHOICES)
    file_name = models.CharField(max_length=255)
    generated_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.file_name} ({self.file_format})"
    
# Notification Table
class InventoryNotification(models.Model):
    NOTIFICATION_TYPES = [
        ('low_stock', 'Low Stock'),
        ('out_of_stock', 'Out of Stock'),
        ('expiry', 'Near Expiry'),
    ]
    
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    notification_type = models.CharField(max_length=20, choices=NOTIFICATION_TYPES)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    recipients = models.ManyToManyField(User, blank=True)  # Who should receive this
    
    def __str__(self):
        return f"{self.product.product_name} - {self.notification_type}"