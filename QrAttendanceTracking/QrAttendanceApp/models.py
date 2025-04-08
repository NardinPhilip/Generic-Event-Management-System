from django.db import models
import qrcode
from io import BytesIO
import base64
from django.core.exceptions import ValidationError
from django.utils.timezone import now
import django.utils.timezone
from django.db import models
import qrcode
from io import BytesIO
import base64
import uuid

class Attendee(models.Model):
    attendee_name = models.CharField(max_length=50, blank=False, null=False)
    attendee_job_title = models.CharField(max_length=50, blank=True, null=True)
    qr_code = models.TextField(unique=True, blank=True)  

    def save(self, *args, **kwargs):
        """Generate a truly unique QR code"""
        if not self.qr_code:
            self.qr_code = f"ATT-{uuid.uuid4().hex[:8]}"  # Generate a unique QR Code
        super().save(*args, **kwargs)

    def get_qr_code_image(self):
        """Generate a QR Code and return it as a base64 image."""
        qr = qrcode.QRCode(version=1, box_size=5, border=2)
        qr.add_data(self.qr_code)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")

        buffered = BytesIO()
        img.save(buffered, format="PNG")
        img_str = base64.b64encode(buffered.getvalue()).decode('utf-8')
        return img_str

    def __str__(self):
        return self.attendee_name


def event_material_upload_path(instance, filename):
    """Dynamic upload path based on event and file type."""
    event_folder = f"event_{instance.event.id}"
    if instance.file.name.lower().endswith(('.jpg', '.jpeg', '.png', '.gif')):
        return f"event_materials/{event_folder}/photos/{now().strftime('%Y/%m/%d')}/{filename}"
    elif instance.file.name.lower().endswith(('.mp4', '.avi', '.mov', '.wmv')):
        return f"event_materials/{event_folder}/videos/{now().strftime('%Y/%m/%d')}/{filename}"
    return f"event_materials/{event_folder}/other/{now().strftime('%Y/%m/%d')}/{filename}"

class Event(models.Model):
    EVENT_STATUS_CHOICES = [
        ('Upcoming', 'Upcoming'),
        ('Ongoing', 'Ongoing'),
        ('Completed', 'Completed'),
        ('Cancelled', 'Cancelled'),
    ]
    event_name = models.CharField(max_length=50, blank=False, null=False)
    event_description = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=EVENT_STATUS_CHOICES, default='Upcoming')
    attendees = models.ManyToManyField('Attendee', related_name="events", through="Attendance")

    def __str__(self):
        return self.event_name

class EventMaterial(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='materials')
    file = models.FileField(upload_to=event_material_upload_path, blank=False, null=False)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.event.event_name} - {self.file.name}"

class EventDateTime(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="event_dates")
    event_datetime = models.DateTimeField()

    def clean(self):
        """Ensure the event datetime is in the future."""
        if self.event_datetime < now():
            raise ValidationError("Event date must be in the future.")

    def __str__(self):
        return f"{self.event.event_name} - {self.event_datetime}"


class Attendance(models.Model):
    ATTENDANCE_STATUS_CHOICES = [
        ('Present', 'Present'),
        ('Absent', 'Absent'),
        ('Late', 'Late'),
    ]

    attendee = models.ForeignKey(Attendee, on_delete=models.CASCADE, related_name="attendance_records")
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="attendance")
    timestamp = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=ATTENDANCE_STATUS_CHOICES, default='Present')

    class Meta:
        unique_together = ('attendee', 'event')  # Ensures an attendee can't check in twice for the same event

    def __str__(self):
        return f"{self.attendee.attendee_name} - {self.event.event_name} ({self.status})"
