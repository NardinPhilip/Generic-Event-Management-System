from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.contrib import messages
from django.forms import modelformset_factory
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST, require_GET
import zipfile
import base64
from io import BytesIO
import json
import uuid
from .models import Event, EventDateTime, Attendee, Attendance
from .forms import EventForm, EventDateTimeFormSet

from django.shortcuts import render, redirect
from django.contrib import messages
from .models import Event, EventDateTime,EventMaterial
from .forms import EventForm, EventDateTimeFormSet
from django.utils import timezone

def event_list(request):
    query = request.GET.get('search', '')
    events = Event.objects.filter(event_name__icontains=query).order_by('-id')

    if request.method == "POST":
        print("POST data:", request.POST)
        form = EventForm(request.POST, request.FILES)
        formset = EventDateTimeFormSet(request.POST, prefix='eventdatetime_set')
        print("Formset forms count:", len(formset.forms))
        # Move cleaned_data access after validation
        if form.is_valid() and formset.is_valid():
            print("Formset cleaned_data:", [f.cleaned_data for f in formset.forms])
            event = form.save(commit=False)
            event_times = []
            for i, subform in enumerate(formset.forms):
                print(f"Subform {i} cleaned_data:", subform.cleaned_data)
                if subform.cleaned_data and subform.cleaned_data.get('event_datetime'):
                    event_datetime = subform.save(commit=False)
                    event_datetime.event = event
                    event_times.append(event_datetime)
                    print(f"Added EventDateTime: {event_datetime.event_datetime}")
                elif subform.errors:
                    print(f"Subform {i} errors:", subform.errors)
            if not event_times:
                messages.error(request, f"Please add at least one valid date and time. Formset errors: {formset.errors}")
                return render(request, 'QrAttendanceApp/event_list.html', {
                    'events': events, 'form': form, 'formset': formset
                })
            event.save()
            for event_datetime in event_times:
                event_datetime.save()
                print(f"Saved EventDateTime: {event_datetime.event_datetime}")
            messages.success(request, "Event and times created successfully")
            return redirect('event_detail', event_id=event.id)
        else:
            print("Form errors:", form.errors)
            print("Formset errors:", formset.errors)
            messages.error(request, f"Error creating event: {form.errors} {formset.errors}")
    else:
        form = EventForm()
        formset = EventDateTimeFormSet(queryset=EventDateTime.objects.none(), prefix='eventdatetime_set')

    return render(request, 'QrAttendanceApp/event_list.html', {
        'events': events, 'form': form, 'formset': formset
    })


from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.core.paginator import Paginator
from django.db import models
from django.http import HttpResponse
from .models import Event, Attendance, Attendee, EventMaterial
import qrcode
from io import BytesIO
from PIL import Image
import zipfile

def event_detail(request, event_id):
    event = get_object_or_404(Event, id=event_id)
    job_filter = request.GET.get('job_filter', '').strip()
    search_query = request.GET.get('search', '').strip()
    attendees = Attendance.objects.filter(event=event).select_related('attendee')
    materials = event.materials.all()
    photos = [m for m in materials if m.file.name.lower().endswith(('.jpg', '.jpeg', '.png', '.gif'))]
    videos = [m for m in materials if m.file.name.lower().endswith(('.mp4', '.avi', '.mov', '.wmv'))]

    # Apply filters
    if job_filter:
        attendees = attendees.filter(attendee__attendee_job_title__iexact=job_filter)
    if search_query:
        attendees = attendees.filter(
            models.Q(attendee__attendee_name__icontains=search_query) |
            models.Q(attendee__attendee_job_title__icontains=search_query)
        )

    # Pagination
    paginator = Paginator(attendees, 5)  # 5 attendees per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

            # Handle attendee edits
    if request.method == 'POST' and 'edit_attendee' in request.POST:
        attendee_id = request.POST.get('attendee_id')
        name = request.POST.get('attendee_name', '').strip()
        job_title = request.POST.get('attendee_job_title', '').strip()
        print(f"Raw POST: {request.POST}")  # Full POST data
        print(f"Extracted: attendee_id={attendee_id}, name='{name}', job_title='{job_title}'")
        attendee = get_object_or_404(Attendee, id=attendee_id)
        
        if not name and not attendee.attendee_name:
            messages.error(request, "Attendee name cannot be empty.")
            return redirect('event_detail', event_id=event_id)
        old_name = attendee.attendee_name
        attendee.attendee_name = name if name else attendee.attendee_name
        attendee.attendee_job_title = job_title if job_title else attendee.attendee_job_title or ''
        print(f"Before Save: name='{attendee.attendee_name}', job_title='{attendee.attendee_job_title}'")
        attendee.save()
        print(f"After Save: name='{attendee.attendee_name}', job_title='{attendee.attendee_job_title}'")
        messages.success(request, f"Updated {old_name} successfully to {attendee.attendee_name}.")
        return redirect('event_detail', event_id=event_id)
    # Handle file uploads (for Materials tab)
    if request.method == 'POST' and 'upload_file' in request.FILES:
        uploaded_files = request.FILES.getlist('upload_file')
        for uploaded_file in uploaded_files:
            if uploaded_file.content_type.startswith(('image/', 'video/')):
                EventMaterial.objects.create(event=event, file=uploaded_file)
                messages.success(request, f"Uploaded {uploaded_file.name} successfully.")
            else:
                messages.error(request, f"{uploaded_file.name} is not a valid image or video.")
        return redirect('event_detail', event_id=event_id)

    job_titles = attendees.values_list('attendee__attendee_job_title', flat=True).distinct()
    time_slots = event.event_dates.all()

    if event.status in ['Ongoing', 'Completed']:
        total_attendees = attendees.count()
        present_count = attendees.filter(status='Present').count()
        absent_count = attendees.filter(status='Absent').count()
        late_count = total_attendees - present_count - absent_count
        total_present = present_count
        total_absent = absent_count
        attendance_ratio = round((present_count / total_attendees * 100) if total_attendees > 0 else 0, 2)
    else:
        total_present = total_absent = late_count = attendance_ratio = 0

    return render(request, 'QrAttendanceApp/event_detail.html', {
        'event': event,
        'attendees': page_obj,
        'page_obj': page_obj,
        'job_titles': job_titles,
        'job_filter': job_filter,
        'search_query': search_query,
        'time_slots': time_slots,
        'total_present': total_present,
        'total_absent': total_absent,
        'late_count': late_count,
        'attendance_ratio': attendance_ratio,
        'photos': photos,
        'videos': videos
    })

def download_qr_code(request, event_id):
    event = get_object_or_404(Event, id=event_id)
    attendee_ids = request.GET.getlist('attendee_ids')  # Get list of selected attendee IDs
    
    if not attendee_ids:  # If no IDs selected, download all
        attendees = Attendance.objects.filter(event=event).select_related('attendee')
    else:
        attendees = Attendance.objects.filter(event=event, attendee__id__in=attendee_ids).select_related('attendee')

    if len(attendees) == 1:  # Single QR code download
        attendee = attendees[0].attendee
        qr = qrcode.QRCode(version=1, box_size=10, border=4)
        qr.add_data(f"{attendee.id}")
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)
        
        response = HttpResponse(buffer, content_type='image/png')
        response['Content-Disposition'] = f'attachment; filename="qr_code_{attendee.attendee_name}.png"'
        return response
    else:  # Multiple QR codes, create a ZIP file
        buffer = BytesIO()
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for attendance in attendees:
                attendee = attendance.attendee
                qr = qrcode.QRCode(version=1, box_size=10, border=4)
                qr.add_data(f"{attendee.id}")
                qr.make(fit=True)
                img = qr.make_image(fill_color="black", back_color="white")
                
                img_buffer = BytesIO()
                img.save(img_buffer, format="PNG")
                zip_file.writestr(f"qr_code_{attendee.attendee_name}.png", img_buffer.getvalue())
        
        buffer.seek(0)
        response = HttpResponse(buffer, content_type='application/zip')
        response['Content-Disposition'] = f'attachment; filename="qr_codes_event_{event_id}.zip"'
        return response


@csrf_exempt
@require_POST
def mark_attendance(request, event_id):
    event = get_object_or_404(Event, id=event_id)
    try:
        data = json.loads(request.body)
        qr_code = data.get('qr_code')
        if not qr_code:
            return JsonResponse({'success': False, 'error': 'No QR code provided'}, status=400)

        attendee = Attendee.objects.filter(qr_code=qr_code).first()
        if not attendee:
            return JsonResponse({'success': False, 'error': 'Attendee not found'}, status=404)

        attendance = Attendance.objects.filter(event=event, attendee=attendee).first()
        if not attendance:
            return JsonResponse({'success': False, 'error': 'Attendance record not found'}, status=404)

        attendance.status = 'Present'
        attendance.save()

        return JsonResponse({
            'success': True,
            'attendee_name': attendee.attendee_name,
            'status': attendance.status
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@require_GET
def get_attendee_name(request, event_id):
    qr_code = request.GET.get('qr_code')
    if not qr_code:
        return JsonResponse({'success': False, 'error': 'No QR code provided'}, status=400)

    event = get_object_or_404(Event, id=event_id)
    try:
        attendee = Attendee.objects.get(qr_code=qr_code)
        attendance = Attendance.objects.filter(event=event, attendee=attendee).first()
        if not attendance:
            return JsonResponse({'success': False, 'error': 'Attendee not registered for this event'}, status=404)

        return JsonResponse({
            'success': True,
            'attendee_name': attendee.attendee_name
        })
    except Attendee.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Attendee not found'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@require_POST
def add_attendee(request, event_id):
    event = get_object_or_404(Event, id=event_id)
    attendee_name = request.POST.get('attendee_name', '').strip()
    attendee_job_title = request.POST.get('attendee_job_title', '').strip() or None

    if not attendee_name:
        return JsonResponse({'success': False, 'error': 'Attendee name is required'}, status=400)

    attendee, created = Attendee.objects.get_or_create(
        attendee_name=attendee_name,
        attendee_job_title=attendee_job_title,
        defaults={'qr_code': f"ATT-{uuid.uuid4().hex[:8]}"}
    )

    attendance, _ = Attendance.objects.get_or_create(
        event=event,
        attendee=attendee,
        defaults={'status': 'Absent'}
    )

    return JsonResponse({
        'success': True,
        'attendee_name': attendee.attendee_name,
        'attendee_id': attendee.id
    })

from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from .models import Event, Attendance

@csrf_exempt
@require_POST
def mark_manual_attendance(request, event_id):
    print("Received request to mark_manual_attendance")
    print("Request POST data:", dict(request.POST))
    print("CSRF token from header:", request.headers.get('X-CSRFToken'))

    try:
        event = get_object_or_404(Event, id=event_id)
        print(f"Event ID: {event_id}, Status: {event.status}")
        
        if event.status not in ['Ongoing', 'Completed']:
            print(f"Event {event_id} is {event.status}, cannot mark attendance")
            response = JsonResponse({'success': False, 'error': 'Event is not ongoing or completed'}, status=400)
            print("Returning response:", response.content.decode())
            return response

        attendee_id = request.POST.get('attendee_id')
        print(f"Attendee ID: {attendee_id}")

        if not attendee_id:
            print("No attendee_id provided")
            response = JsonResponse({'success': False, 'error': 'Attendee is required'}, status=400)
            print("Returning response:", response.content.decode())
            return response

        attendance = Attendance.objects.get(event=event, attendee_id=attendee_id)
        print(f"Found attendance: {attendance}, Attendee: {attendance.attendee.attendee_name}")
        attendance.status = 'Present'
        attendance.save()
        print(f"Updated attendance to Present for {attendance.attendee.attendee_name}")
        response = JsonResponse({
            'success': True,
            'attendee_name': attendance.attendee.attendee_name,
            'status': attendance.status
        })
        print("Returning response:", response.content.decode())
        return response

    except Attendance.DoesNotExist:
        print(f"No attendance record found for event {event_id} and attendee {attendee_id}")
        response = JsonResponse({'success': False, 'error': 'Attendance record not found'}, status=404)
        print("Returning response:", response.content.decode())
        return response
    except Exception as e:
        print(f"Unexpected error occurred: {str(e)}")
        response = JsonResponse({'success': False, 'error': str(e)}, status=500)
        print("Returning response:", response.content.decode())
        return response
    
def attendance_summary(request, event_id):
    event = get_object_or_404(Event, id=event_id)
    if event.status not in ['Ongoing', 'Completed']:
        return JsonResponse({"error": "Event is not ongoing or completed"}, status=400)

    job_filter = request.GET.get('job_filter', '').strip()
    attendees = Attendance.objects.filter(event=event).select_related('attendee')
    if job_filter:
        attendees = attendees.filter(attendee__attendee_job_title__iexact=job_filter)

    total_attendees = attendees.count()
    present_count = attendees.filter(status='Present').count()
    absent_count = total_attendees - present_count
    attendance_ratio = round((present_count / total_attendees * 100) if total_attendees > 0 else 0, 2)

    return JsonResponse({
        "total": total_attendees,
        "present": present_count,
        "absent": absent_count,
        "ratio": attendance_ratio
    })
import pandas as pd
def download_attendance_sheet(request, event_id):
    event = get_object_or_404(Event, id=event_id)
    
    # Fetch attendance data
    attendance_records = Attendance.objects.filter(event=event).select_related('attendee')
    
    # Prepare data for the sheet
    data = {
        'Name': [record.attendee.attendee_name for record in attendance_records],
        'Job Title': [record.attendee.attendee_job_title or 'N/A' for record in attendance_records],
        'Attendance Status': [record.status for record in attendance_records],
        'Timestamp': [record.timestamp.strftime('%Y-%m-%d %H:%M:%S') for record in attendance_records],
    }
    
    # Create a DataFrame
    df = pd.DataFrame(data)
    
    # Write to Excel in memory
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
        df.to_excel(writer, sheet_name=f"{event.event_name}_Attendance", index=False)
    
    buffer.seek(0)
    response = HttpResponse(
        buffer,
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="{event.event_name}_Attendance.xlsx"'
    return response