import pandas as pd
from .models import Attendee

def process_attendee_excel(file):
    """Reads an Excel file and creates attendees."""
    df = pd.read_excel(file)

    required_columns = {'attendee_name', 'attendee_job_title'}
    if not required_columns.issubset(df.columns):
        raise ValueError(f"Excel file must contain columns: {', '.join(required_columns)}")

    attendees = []
    for _, row in df.iterrows():
        attendee, created = Attendee.objects.get_or_create(
            attendee_name=row['attendee_name'],
            attendee_job_title=row.get('attendee_job_title', '')
        )
        attendees.append(attendee)

    return attendees
