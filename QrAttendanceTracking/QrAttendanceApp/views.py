from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.contrib import messages
from django.forms import modelformset_factory
from django.views.decorators.csrf import csrf_exempt
from .models import Event, EventDateTime, Attendee, Attendance
from .forms import EventForm, EventDateTimeFormSet
import zipfile
import base64
from io import BytesIO
from PIL import Image
from django.utils.timezone import now

from django.shortcuts import render, redirect
from django.contrib import messages
from .models import Event, EventDateTime
from .forms import EventForm, EventDateTimeFormSet

def event_list(request):
    query = request.GET.get('search', '')
    events = Event.objects.filter(event_name__icontains=query).order_by('-id')

    if request.method == "POST":
        form = EventForm(request.POST, request.FILES)
        formset = EventDateTimeFormSet(request.POST)
        if form.is_valid() and formset.is_valid():
            event = form.save()
            for subform in formset:
                if subform.cleaned_data:
                    event_datetime = subform.save(commit=False)
                    event_datetime.event = event/bus
                    event_datetime.save()
            messages.success(request, "Event created successfully")
            return redirect('event_detail', event_id=event.id)
        else:
            messages.error(request, "There was an error creating the event.")
    else:
        form = EventForm()
        formset = EventDateTimeFormSet(queryset=EventDateTime.objects.none())

    return render(request, 'QrAttendanceApp/event_list.html', {
        'events': events,
        'form': form,
        'formset': formset
    })

def event_detail(request, event_id):
    event = get_object_or_404(Event, id=event_id)
    job_filter = request.GET.get('job_filter', '').strip()

    # Fetch attendees through the Attendance model
    attendees = Attendance.objects.filter(event=event).select_related('attendee')
    print(f"Attendees for event {event.event_name} (ID: {event.id}): {[(a.attendee.attendee_name, a.status) for a in attendees]}")

    if job_filter:
        attendees = attendees.filter(attendee__attendee_job_title__iexact=job_filter)
        print(f"Attendees after job filter '{job_filter}': {[(a.attendee.attendee_name, a.status) for a in attendees]}")

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
        'attendees': attendees,
        'job_titles': job_titles,
        'time_slots': time_slots,
        'job_filter': job_filter,
        'total_present': total_present,
        'total_absent': total_absent,
        'late_count': late_count,
        'attendance_ratio': attendance_ratio
    })

def download_qr_codes(request, event_id):
    event = get_object_or_404(Event, id=event_id)
    # Fetch attendees through Attendance to ensure only registered attendees are included
    attendees = Attendance.objects.filter(event=event).select_related('attendee')

    if not attendees:
        messages.warning(request, "No attendees found for this event")
        return redirect('event_detail', event_id=event.id)

    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for attendance in attendees:
            attendee = attendance.attendee
            qr_data = attendee.get_qr_code_image()
            qr_bytes = base64.b64decode(qr_data)
            zip_file.writestr(f"{attendee.attendee_name}_QR.png", qr_bytes)

    zip_buffer.seek(0)
    response = HttpResponse(zip_buffer, content_type='application/zip')
    response['Content-Disposition'] = f'attachment; filename="QR_Codes_{event.event_name}.zip"'
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

@csrf_exempt
def get_attendee_details(request):
    if request.method == "POST":
        qr_code = request.POST.get('qr_code')
        event_id = request.POST.get('event_id')
        try:
            attendee = Attendee.objects.get(qr_code=qr_code)
            event = Event.objects.get(id=event_id, status='Ongoing')
            # Check if the attendee is linked via Attendance
            if not Attendance.objects.filter(event=event, attendee=attendee).exists():
                return JsonResponse({'success': False, 'message': 'Attendee is not registered for this event.'})
            return JsonResponse({
                'success': True,
                'attendee_id': attendee.id,
                'name': attendee.attendee_name,
                'job_title': attendee.attendee_job_title or "N/A",
                'event_name': event.event_name
            })
        except Attendee.DoesNotExist:
            return JsonResponse({'success': False, 'message': 'Attendee not found.'})
        except Event.DoesNotExist:
            return JsonResponse({'success': False, 'message': 'Event not found or not ongoing.'})
    return JsonResponse({'success': False, 'message': 'Invalid request.'})

@csrf_exempt
def confirm_attendance(request):
    if request.method == "POST":
        attendee_id = request.POST.get('attendee_id')
        event_id = request.POST.get('event_id')
        try:
            attendee = Attendee.objects.get(id=attendee_id)
            event = Event.objects.get(id=event_id, status='Ongoing')
            # Ensure the attendance record exists or create it
            attendance, created = Attendance.objects.get_or_create(
                event=event,
                attendee=attendee,
                defaults={'status': 'Present'}
            )
            if not created and attendance.status != 'Present':
                attendance.status = 'Present'
                attendance.save()
            return JsonResponse({'success': True})
        except Attendee.DoesNotExist:
            return JsonResponse({'success': False, 'message': 'Attendee not found.'})
        except Event.DoesNotExist:
            return JsonResponse({'success': False, 'message': 'Event not found or not ongoing.'})
    return JsonResponse({'success': False, 'message': 'Invalid request.'})

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
import json
@csrf_exempt
@require_POST
def mark_attendance(request, event_id):
    event = get_object_or_404(Event, id=event_id)
    try:
        data = json.loads(request.body)
        qr_code = data.get('qr_code')
        if not qr_code:
            return JsonResponse({'success': False, 'error': 'No QR code provided'}, status=400)

        # Find the attendee with the matching QR code
        attendee = Attendee.objects.filter(qr_code=qr_code).first()
        if not attendee:
            return JsonResponse({'success': False, 'error': 'Attendee not found'}, status=404)

        # Find the attendance record for this event and attendee
        attendance = Attendance.objects.filter(event=event, attendee=attendee).first()
        if not attendance:
            return JsonResponse({'success': False, 'error': 'Attendance record not found'}, status=404)

        # Update attendance status to "Present" (or "Late" if applicable)
        attendance.status = 'Present'  # Add logic for "Late" if needed
        attendance.save()

        return JsonResponse({
            'success': True,
            'attendee_name': attendee.attendee_name,
            'status': attendance.status
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)
    from django.http import JsonResponse
from django.views.decorators.http import require_GET
from .models import Attendee, Event

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