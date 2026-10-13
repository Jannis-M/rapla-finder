import streamlit as st
import requests
import re
from datetime import datetime, timedelta

def get_ical_events(url, exclude_keywords):
    """Wandelt die Rapla-HTML-URL in eine iCal-URL um und liest die Termine aus."""
    user_match = re.search(r'user=([^&]+)', url)
    file_match = re.search(r'file=([^&]+)', url)
    
    if not user_match or not file_match:
        st.error("Ungültige Rapla-URL")
        return []
        
    user = user_match.group(1)
    file = file_match.group(1)
    
    ical_url = f"https://rapla.dhbw.de/rapla?page=ical&user={user}&file={file}"
    
    try:
        response = requests.get(ical_url)
        response.raise_for_status()
        lines = response.text.splitlines()
        
        events = []
        in_event = False
        current_event = {}
        
        for line in lines:
            if line.startswith("BEGIN:VEVENT"):
                in_event = True
                current_event = {}
            elif line.startswith("END:VEVENT"):
                in_event = False
                summary = current_event.get("SUMMARY", "")
                skip = False
                for keyword in exclude_keywords:
                    if keyword.lower() in summary.lower():
                        skip = True
                        break
                        
                if not skip and "DTSTART" in current_event and "DTEND" in current_event:
                    events.append(current_event)
            elif in_event:
                if line.startswith("SUMMARY:"):
                    current_event["SUMMARY"] = line[8:]
                elif line.startswith("DTSTART"):
                    match = re.search(r':(\d{8}T\d{6})', line)
                    if match:
                        current_event["DTSTART"] = datetime.strptime(match.group(1), "%Y%m%dT%H%M%S")
                elif line.startswith("DTEND"):
                    match = re.search(r':(\d{8}T\d{6})', line)
                    if match:
                        current_event["DTEND"] = datetime.strptime(match.group(1), "%Y%m%dT%H%M%S")
                        
        return events
        
    except Exception as e:
        st.error(f"Fehler beim Laden von {user}: {e}")
        return []

st.title("DHBW Termin-Finder 📅")
st.write("Die Kalender werden über den offiziellen iCal-Export synchronisiert. Bestimmte Vorlesungen werden ignoriert.")

# --- NEU: Wochen-Auswahl ---
week_offset = st.slider(
    "Welche Woche möchtest du checken?", 
    min_value=0, 
    max_value=4, 
    value=0, 
    format="In %d Woche(n)"
)
if week_offset == 0:
    st.info("Gewählt: **Diese Woche**")
elif week_offset == 1:
    st.info("Gewählt: **Nächste Woche**")
else:
    st.info(f"Gewählt: **In {week_offset} Wochen**")
# ---------------------------

# Hardcoded Kalender mit den Vorgaben
calendars = [
    {
        "url": "https://rapla.dhbw.de/rapla/calendar?user=schraff.k%40vw.ba.ba-ravensburg.de&file=TFS24",
        "exclude": ["Kraftfahrzeuge", "Qualitätsmanagement", "Studienarbeit"]
    },
    {
        "url": "https://rapla.dhbw.de/rapla/calendar?user=brath%40vw.ba.ba-ravensburg.de&file=Stundenplan+TWI25-2",
        "exclude": []
    },
    {
        "url": "https://rapla.dhbw.de/rapla/internal_calendar?user=muenzer@vw.ba.ba-ravensburg.de&file=TFE24-2",
        "exclude": ["künstliche Intelligenz", "STA Mercedes"]
    }
]

if st.button("Gemeinsame freie Zeit finden", type="primary"):
    with st.spinner('Kalender werden abgeglichen...'):
        all_events = []
        for cal in calendars:
            events = get_ical_events(cal["url"], cal["exclude"])
            all_events.extend(events)
            
        # Blockierte 15-Minuten-Slots berechnen
        blocked_slots = set()
        for event in all_events:
            start_dt = event['DTSTART']
            end_dt = event['DTEND']
            
            curr = start_dt
            while curr < end_dt:
                blocked_slots.add(curr)
                curr += timedelta(minutes=15)

        # Start der ausgewählten Woche berechnen (Montag)
        today = datetime.today()
        # Montag dieser Woche:
        start_of_current_week = today - timedelta(days=today.weekday()) 
        start_of_current_week = start_of_current_week.replace(hour=8, minute=0, second=0, microsecond=0)
        
        # Auf die gewählte Woche verschieben (+ 7 Tage pro week_offset)
        start_of_target_week = start_of_current_week + timedelta(weeks=week_offset)
        
        st.subheader("Eure Freistunden:")
        
        tage = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag"]
        found_any = False
        
        for day in range(5):
            current_day = start_of_target_week + timedelta(days=day)
            free_periods = []
            current_free_start = None
            
            # Das Tagesraster abarbeiten (jetzt von 8 bis 23 Uhr)
            for hour in range(8, 23):
                for minute in (0, 15, 30, 45):
                    slot = current_day.replace(hour=hour, minute=minute)
                    if slot not in blocked_slots:
                        if current_free_start is None:
                            current_free_start = slot
                    else:
                        if current_free_start is not None:
                            free_periods.append((current_free_start, slot))
                            current_free_start = None
                            
            if current_free_start is not None:
                end_of_day = current_day.replace(hour=23, minute=0)
                free_periods.append((current_free_start, end_of_day))
                
            # Nur Zeitfenster anzeigen, die mindestens 45 Minuten lang sind
            valid_periods = [(s, e) for s, e in free_periods if (e - s).total_seconds() >= 2700]
            
            if valid_periods:
                found_any = True
                st.write(f"**{tage[day]}, {current_day.strftime('%d.%m.')}**")
                for start, end in valid_periods:
                    st.success(f"✅ {start.strftime('%H:%M')} bis {end.strftime('%H:%M')} Uhr")
                    
        if not found_any:
            st.warning("In dieser Woche habt ihr leider keine gemeinsamen Freistunden (zwischen 8 und 23 Uhr).")