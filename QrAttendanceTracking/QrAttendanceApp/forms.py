from django import forms
from django.forms import modelformset_factory
from .models import Event, EventDateTime, Attendee, Attendance
import pandas as pd
from django.core.exceptions import ValidationError
from django.utils.timezone import now

class EventForm(forms.ModelForm):
    attendee_file = forms.FileField(
        required=False,
        label="Upload Attendee Excel",
        help_text="Upload an Excel file with columns 'Name' and 'Job Title'",
        widget=forms.FileInput(attrs={'accept': '.xls,.xlsx', 'class': 'form-control'})
    )

    class Meta:
        model = Event
        fields = ['event_name', 'event_description', 'status']
        widgets = {
            'event_name': forms.TextInput(attrs={'class': 'form-control'}),
            'event_description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'status': forms.Select(attrs={'class': 'form-control'}),
        }

    def clean_attendee_file(self):
        attendee_file = self.cleaned_data.get('attendee_file')
        if attendee_file:
            if not attendee_file.name.endswith(('.xls', '.xlsx')):
                raise ValidationError("Only Excel files (.xls, .xlsx) are supported.")
            try:
                df = pd.read_excel(attendee_file)
                print("Excel file contents:", df.to_dict())
                required_columns = {'Name'}
                if not required_columns.issubset(df.columns):
                    raise ValidationError("Excel file must contain a 'Name' column.")
            except Exception as e:
                raise ValidationError(f"Error reading Excel file: {str(e)}")
            attendee_file.seek(0)
        return attendee_file

    def save(self, commit=True):
        event = super().save(commit=False)
        if commit:
            event.save()
        print(f"Event saved: {event.event_name} (ID: {event.id})")

        attendee_file = self.cleaned_data.get('attendee_file')
        if attendee_file:
            try:
                df = pd.read_excel(attendee_file)
                existing_attendees = set(event.attendees.values_list('attendee_name', flat=True))
                print(f"Existing attendees: {existing_attendees}")

                for _, row in df.iterrows():
                    name = row.get("Name")
                    if pd.isna(name) or not name or name in existing_attendees:
                        print(f"Skipping attendee: {name} (already exists or invalid)")
                        continue
                    attendee, created = Attendee.objects.get_or_create(
                        attendee_name=name,
                        defaults={'attendee_job_title': row.get("Job Title", "") or ""}
                    )
                    print(f"Attendee {attendee.attendee_name} (ID: {attendee.id}) {'created' if created else 'retrieved'}")

                    attendance, created = Attendance.objects.get_or_create(
                        event=event,
                        attendee=attendee,
                        defaults={'status': 'Absent'}
                    )
                    print(f"Attendance for {attendee.attendee_name} in event {event.event_name} {'created' if created else 'already exists'} with status: {attendance.status}")
                    existing_attendees.add(name)
            except Exception as e:
                print(f"Error processing attendees: {str(e)}")
                if commit:
                    event.delete()
                raise ValidationError(f"Error processing attendees: {str(e)}")
        return event

class EventDateTimeForm(forms.ModelForm):
    class Meta:
        model = EventDateTime
        fields = ['event_datetime']
        widgets = {
            'event_datetime': forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-control'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        event_datetime = cleaned_data.get('event_datetime')
        if event_datetime and event_datetime < now():
            raise ValidationError("Event datetime must be in the future.")
        return cleaned_data

EventDateTimeFormSet = modelformset_factory(
    EventDateTime,
    form=EventDateTimeForm,
    extra=0,  # Changed to 0 to match dynamic addition
    can_delete=True,
)