from django.urls import path
from . import views
from django.conf import settings
from django.conf.urls.static import static
urlpatterns = [
    path('', views.event_list, name='event_list'),
    path('event/<int:event_id>/', views.event_detail, name='event_detail'),
    # path('event/<int:event_id>/download_qr_codes/', views.download_qr_codes, name='download_qr_codes'),
    path('event/<int:event_id>/mark_attendance/', views.mark_attendance, name='mark_attendance'),
    path('event/<int:event_id>/attendee_name/', views.get_attendee_name, name='get_attendee_name'),  # New route
    path('event/<int:event_id>/attendance_summary/', views.attendance_summary, name='attendance_summary'),
    # path('attendee_details/', views.get_attendee_details, name='get_attendee_details'),
    # path('confirm_attendance/', views.confirm_attendance, name='confirm_attendance'),
    path('event/<int:event_id>/', views.event_detail, name='event_detail'),
    path('event/<int:event_id>/add_attendee/', views.add_attendee, name='add_attendee'),
    path('event/<int:event_id>/mark_manual_attendance/', views.mark_manual_attendance, name='mark_manual_attendance'),
    path('event/<int:event_id>/download_attendance_sheet/', views.download_attendance_sheet, name='download_attendance_sheet'),\
    path('event/<int:event_id>/download_qr_code/', views.download_qr_code, name='download_qr_code'),
    # ... other paths ...    # Add other paths as needed

]
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)