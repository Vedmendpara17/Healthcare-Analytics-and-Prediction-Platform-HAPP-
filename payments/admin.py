from django.contrib import admin
from .models import Payment, Invoice, Refund

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('payment_id', 'transaction_id', 'patient', 'doctor', 'total_amount', 'payment_method', 'payment_status', 'invoice_number', 'created_at')
    list_filter = ('payment_status', 'payment_method', 'created_at')
    search_fields = ('payment_id', 'transaction_id', 'invoice_number', 'patient__username', 'patient__first_name', 'patient__last_name', 'doctor__user__first_name')
    readonly_fields = ('payment_id', 'transaction_id', 'invoice_number', 'created_at', 'updated_at')

@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ('invoice_number', 'payment', 'generated_at')
    search_fields = ('invoice_number', 'payment__payment_id')

@admin.register(Refund)
class RefundAdmin(admin.ModelAdmin):
    list_display = ('refund_id', 'payment', 'refund_amount', 'refund_status', 'processed_by', 'created_at')
    list_filter = ('refund_status', 'created_at')
    search_fields = ('refund_id', 'payment__payment_id', 'payment__invoice_number')
