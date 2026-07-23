def notifications_context(request):
    if request.user.is_authenticated:
        from core.models import Notification
        unread_notifications = Notification.objects.filter(user=request.user, is_read=False).order_by('-created_at')[:5]
        unread_count = Notification.objects.filter(user=request.user, is_read=False).count()
        return {
            'unread_notifications': unread_notifications,
            'unread_notifications_count': unread_count,
        }
    return {
        'unread_notifications': [],
        'unread_notifications_count': 0,
    }
